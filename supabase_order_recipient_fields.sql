alter table public.orders
add column if not exists recipient_name text,
add column if not exists recipient_address text;
