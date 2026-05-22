-- imowi NOC Copilot — esquema inicial (Supabase / PostgreSQL)
-- Ejecutar en SQL Editor del proyecto Supabase

create table if not exists tickets (
  id text primary key,
  cooperativa text not null default '',
  modulo text not null default 'General',
  modulo_id text not null default 'general',
  linea text not null default '',
  dispositivo text not null default '',
  descripcion text not null default '',
  estado text not null default 'Abierto'
    check (estado in ('Abierto', 'En Revisión', 'Cerrado')),
  resolucion text not null default '',
  tipo_caso text not null default 'escalamiento',
  creado_por text not null default '',
  fecha timestamptz not null default now(),
  fecha_actualizacion timestamptz
);

create index if not exists idx_tickets_creado_por on tickets (creado_por);
create index if not exists idx_tickets_estado on tickets (estado);
create index if not exists idx_tickets_fecha on tickets (fecha desc);

-- RLS (activar después de definir auth). Demo: service_role desde el backend.
-- alter table tickets enable row level security;
