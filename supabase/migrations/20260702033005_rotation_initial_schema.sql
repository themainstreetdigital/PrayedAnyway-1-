-- ============================================================
-- Rotation — initial schema
-- Postgres / Supabase. Run in the SQL editor or as a migration.
-- Mirrors section 3 of the build plan.
-- ============================================================

-- Supabase provides auth.users. Our public.users row extends it 1:1.
-- (id references auth.users so a profile is created per authenticated user.)

create table public.users (
  id          uuid primary key references auth.users(id) on delete cascade,
  name        text,
  email       text,
  phone       text,                       -- nullable; only if the user opts into SMS
  created_at  timestamptz not null default now()
);

-- ------------------------------------------------------------
-- Club: the durable group + its concept
-- ------------------------------------------------------------
create table public.clubs (
  id                     uuid primary key default gen_random_uuid(),
  name                   text not null,
  template_type          text,                              -- 'cookbook' | 'book' | ... | 'blank'
  cadence                text,                              -- free text: "every 3rd Thursday"
  location_mode          text not null default 'fixed'
                           check (location_mode in ('fixed','rotating')),
  location               text,                              -- used when location_mode = 'fixed'
  current_host_index     int  not null default 0,           -- pointer into the rotation
  default_prep_template  text,                              -- Plus: pre-fills each new session
  created_by             uuid references public.users(id) on delete set null,
  created_at             timestamptz not null default now()
);

-- ------------------------------------------------------------
-- Membership: which users belong to which clubs (+ host order)
-- host_position drives the rotating-host queue for the club.
-- ------------------------------------------------------------
create table public.memberships (
  id             uuid primary key default gen_random_uuid(),
  club_id        uuid not null references public.clubs(id) on delete cascade,
  user_id        uuid not null references public.users(id) on delete cascade,
  role           text not null default 'member'
                   check (role in ('organizer','member')),
  host_position  int,                                       -- order in the host rotation (nullable)
  joined_at      timestamptz not null default now(),
  unique (club_id, user_id)
);

-- ------------------------------------------------------------
-- RoleSlot: the Club's durable role schema (the seed defaults,
-- copied to each session as role_assignments)
-- ------------------------------------------------------------
create table public.role_slots (
  id              uuid primary key default gen_random_uuid(),
  club_id         uuid not null references public.clubs(id) on delete cascade,
  label           text not null,
  type            text not null check (type in ('fixed','rotating','open')),
  fixed_user_id   uuid references public.users(id) on delete set null,  -- for 'fixed'
  sort_order      int  not null default 0
);

-- ------------------------------------------------------------
-- Session: one instance of a club, with a lifecycle
-- ------------------------------------------------------------
create table public.sessions (
  id                  uuid primary key default gen_random_uuid(),
  club_id             uuid not null references public.clubs(id) on delete cascade,
  status              text not null default 'proposing'
                        check (status in ('proposing','confirmed','completed','cancelled')),
  confirmed_datetime  timestamptz,                          -- null until locked
  location            text,                                 -- resolved at confirm time
  host_user_id        uuid references public.users(id) on delete set null,  -- resolved at confirm
  prep_notes          text,
  prep_visibility     text not null default 'shared'
                        check (prep_visibility in ('shared','hidden_until_start')),  -- hidden = Plus
  recap_note          text,                                 -- added on completion
  created_at          timestamptz not null default now(),
  completed_at        timestamptz
);

-- ------------------------------------------------------------
-- Date options proposed for a session, and votes on them
-- ------------------------------------------------------------
create table public.date_options (
  id          uuid primary key default gen_random_uuid(),
  session_id  uuid not null references public.sessions(id) on delete cascade,
  datetime    timestamptz not null
);

create table public.votes (
  id              uuid primary key default gen_random_uuid(),
  date_option_id  uuid not null references public.date_options(id) on delete cascade,
  member_id       uuid not null references public.users(id) on delete cascade,
  mark            text not null check (mark in ('yes','no')),  -- deliberately no 'maybe'
  created_at      timestamptz not null default now(),
  unique (date_option_id, member_id)
);

-- ------------------------------------------------------------
-- RoleAssignment: who's doing what for THIS session
-- (copied from role_slots at session creation; open slots claimed)
-- ------------------------------------------------------------
create table public.role_assignments (
  id            uuid primary key default gen_random_uuid(),
  session_id    uuid not null references public.sessions(id) on delete cascade,
  label         text not null,
  type          text not null check (type in ('fixed','rotating','open')),
  user_id       uuid references public.users(id) on delete set null,  -- null = open/unclaimed
  claimed_at    timestamptz,
  sort_order    int not null default 0
);

-- ------------------------------------------------------------
-- Consent: per member, per channel — the legal record for SMS/email
-- ------------------------------------------------------------
create table public.consents (
  id                     uuid primary key default gen_random_uuid(),
  member_id              uuid not null references public.users(id) on delete cascade,
  channel                text not null check (channel in ('sms','email')),
  status                 text not null default 'active'
                           check (status in ('active','stopped')),
  consent_text_version   text,                              -- exact wording they agreed to
  consented_at           timestamptz not null default now(),
  stopped_at             timestamptz,
  unique (member_id, channel)
);

-- ------------------------------------------------------------
-- Message templates (system-provided, per category)
-- ------------------------------------------------------------
create table public.message_templates (
  id                uuid primary key default gen_random_uuid(),
  category          text not null check (category in
                      ('reminder','prep_notes','roster_nudge','change_of_plan','host_rotation')),
  body_with_tokens  text not null   -- "Reminder: {club} is {time} at {place}. Reply STOP to opt out."
);

-- ------------------------------------------------------------
-- ScheduledMessage: queued/automatic outbound messages
-- Tokens resolve at SEND time (worker fills resolved_body then).
-- ------------------------------------------------------------
create table public.scheduled_messages (
  id               uuid primary key default gen_random_uuid(),
  club_id          uuid not null references public.clubs(id) on delete cascade,
  session_id       uuid references public.sessions(id) on delete cascade,
  template_id      uuid references public.message_templates(id) on delete set null,
  trigger_type     text not null check (trigger_type in ('time','event')),
  send_at          timestamptz,                             -- for trigger_type = 'time'
  trigger_event    text,                                    -- for trigger_type = 'event' (e.g. 'roles_opened')
  audience_filter  text,                                    -- e.g. "consented AND not_claimed_a_role"
  resolved_body    text,                                    -- filled at send time
  status           text not null default 'queued'
                     check (status in ('queued','sent','cancelled')),
  created_by       uuid references public.users(id) on delete set null,
  created_at       timestamptz not null default now()
);

-- ------------------------------------------------------------
-- DeliveryLog: one row per recipient per message (audit trail)
-- ------------------------------------------------------------
create table public.delivery_logs (
  id           uuid primary key default gen_random_uuid(),
  message_id   uuid not null references public.scheduled_messages(id) on delete cascade,
  member_id    uuid not null references public.users(id) on delete cascade,
  channel      text not null check (channel in ('sms','email','in_app')),
  status       text not null,                               -- 'sent' | 'failed' | 'delivered' ...
  provider_id  text,                                        -- e.g. Twilio message SID
  sent_at      timestamptz not null default now()
);

-- ------------------------------------------------------------
-- Helpful indexes for the common lookups
-- ------------------------------------------------------------
create index on public.memberships (club_id);
create index on public.memberships (user_id);
create index on public.role_slots (club_id);
create index on public.sessions (club_id, status);
create index on public.date_options (session_id);
create index on public.votes (date_option_id);
create index on public.role_assignments (session_id);
create index on public.scheduled_messages (status, send_at);
create index on public.delivery_logs (message_id);

-- ============================================================
-- Row Level Security — enable and gate by club membership.
-- Principle: you can see/act on a club only if you're a member;
-- writes to a club's structure are limited to organizers.
-- (These are starting policies — tighten per-action as you build.)
-- ============================================================

alter table public.users              enable row level security;
alter table public.clubs              enable row level security;
alter table public.memberships        enable row level security;
alter table public.role_slots         enable row level security;
alter table public.sessions           enable row level security;
alter table public.date_options       enable row level security;
alter table public.votes              enable row level security;
alter table public.role_assignments   enable row level security;
alter table public.consents           enable row level security;
alter table public.message_templates  enable row level security;
alter table public.scheduled_messages enable row level security;
alter table public.delivery_logs      enable row level security;

-- A user can read/update their own profile.
create policy "own profile - select" on public.users
  for select using (auth.uid() = id);
create policy "own profile - update" on public.users
  for update using (auth.uid() = id);
create policy "own profile - insert" on public.users
  for insert with check (auth.uid() = id);

-- Helper: is the current user a member of a given club?
create or replace function public.is_club_member(target_club uuid)
returns boolean
language sql security definer stable set search_path = '' as $$
  select exists (
    select 1 from public.memberships m
    where m.club_id = target_club and m.user_id = auth.uid()
  );
$$;

-- Helper: is the current user an organizer of a given club?
create or replace function public.is_club_organizer(target_club uuid)
returns boolean
language sql security definer stable set search_path = '' as $$
  select exists (
    select 1 from public.memberships m
    where m.club_id = target_club
      and m.user_id = auth.uid()
      and m.role = 'organizer'
  );
$$;

-- Clubs: members can read; organizers can update; any authed user can create.
create policy "club - member read"    on public.clubs
  for select using (public.is_club_member(id));
create policy "club - organizer edit" on public.clubs
  for update using (public.is_club_organizer(id));
create policy "club - create"         on public.clubs
  for insert with check (auth.uid() = created_by);

-- Memberships: members of a club can see its roster.
create policy "membership - read" on public.memberships
  for select using (public.is_club_member(club_id));
-- Bootstrap: the club's creator can add THEMSELVES to their own club
-- (this is what lets the "create club -> become organizer" flow work, since
-- clubs insert is allowed but membership insert would otherwise be blocked).
-- Inviting OTHER members is still a deferred, organizer-scoped write path.
create policy "membership - creator self-join" on public.memberships
  for insert with check (
    user_id = auth.uid()
    and exists (
      select 1 from public.clubs c
      where c.id = club_id and c.created_by = auth.uid()
    )
  );

-- Sessions and their children: readable by club members.
create policy "session - read" on public.sessions
  for select using (public.is_club_member(club_id));
create policy "date_options - read" on public.date_options
  for select using (public.is_club_member(
    (select club_id from public.sessions s where s.id = session_id)));
create policy "role_assignments - read" on public.role_assignments
  for select using (public.is_club_member(
    (select club_id from public.sessions s where s.id = session_id)));

-- Votes: a member can cast/see votes for sessions in their clubs.
create policy "votes - read" on public.votes
  for select using (public.is_club_member(
    (select s.club_id from public.date_options d
       join public.sessions s on s.id = d.session_id
      where d.id = date_option_id)));
create policy "votes - cast" on public.votes
  for insert with check (member_id = auth.uid() and public.is_club_member(
    (select s.club_id from public.date_options d
       join public.sessions s on s.id = d.session_id
      where d.id = date_option_id)));
create policy "votes - change own" on public.votes
  for update using (member_id = auth.uid());

-- Consents: a user manages only their own.
create policy "consent - own" on public.consents
  for all using (member_id = auth.uid()) with check (member_id = auth.uid());

-- Message templates: system-provided reference data, readable by any signed-in
-- user. Writes are intentionally left to the service role / seed migrations.
create policy "message_templates - read" on public.message_templates
  for select to authenticated using (true);

-- NOTE: role_slots, scheduled_messages, delivery_logs, and the write paths
-- for sessions/date_options/role_assignments still need organizer-scoped
-- policies before real users. So does the rest of the memberships write path
-- (inviting/removing members, changing roles) beyond the creator bootstrap
-- above. Start restrictive; open per-action.
