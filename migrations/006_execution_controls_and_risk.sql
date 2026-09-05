alter table public.weeg_settings
  add column if not exists enable_short_signals boolean not null default false,
  add column if not exists long_min_confidence integer not null default 85,
  add column if not exists long_allow_ranging boolean not null default false,
  add column if not exists long_allow_mid_cap boolean not null default false,
  add column if not exists fee_rate numeric not null default 0.0004,
  add column if not exists slippage_rate numeric not null default 0.0002,
  add column if not exists account_equity numeric;

alter table public.weeg_trades
  add column if not exists signal_before_filters text,
  add column if not exists filter_vetoes jsonb not null default '[]'::jsonb,
  add column if not exists gross_pnl numeric,
  add column if not exists fees_and_slippage_pct numeric,
  add column if not exists risk_amount numeric,
  add column if not exists position_size numeric,
  add column if not exists notional numeric;
