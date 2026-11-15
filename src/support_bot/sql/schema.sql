-- Idempotent. gen_random_uuid() is built into PostgreSQL 13+.

CREATE TABLE IF NOT EXISTS customers (
    customer_id bigserial   PRIMARY KEY,
    name        text        NOT NULL,
    email       text        NOT NULL UNIQUE,
    phone       text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
    order_id     text          PRIMARY KEY,
    customer_id  bigint        NOT NULL REFERENCES customers(customer_id),
    status       text          NOT NULL,
    total_amount numeric(10,2) NOT NULL,
    placed_at    timestamptz   NOT NULL DEFAULT now(),
    delivered_at timestamptz,
    CONSTRAINT orders_status_known CHECK (
        status IN ('processing', 'shipped', 'delivered', 'cancelled', 'refunded')),
    CONSTRAINT orders_amount_positive CHECK (total_amount >= 0),
    CONSTRAINT orders_delivered_has_date CHECK (status <> 'delivered' OR delivered_at IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS orders_order_id_upper_idx ON orders (upper(order_id));
CREATE INDEX IF NOT EXISTS orders_customer_idx ON orders (customer_id);

CREATE TABLE IF NOT EXISTS order_items (
    item_id    bigserial     PRIMARY KEY,
    order_id   text          NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    name       text          NOT NULL,
    quantity   int           NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_price numeric(10,2) NOT NULL CHECK (unit_price >= 0)
);
CREATE INDEX IF NOT EXISTS order_items_order_idx ON order_items (order_id);

-- Server-side conversation state. The model can never write these fields directly.
CREATE TABLE IF NOT EXISTS sessions (
    session_id        uuid        PRIMARY KEY,
    verified_order_id text        REFERENCES orders(order_id),
    failed_attempts   int         NOT NULL DEFAULT 0,
    locked            boolean     NOT NULL DEFAULT false,
    user_turns        int         NOT NULL DEFAULT 0,
    pending_action    text        CHECK (pending_action IN ('cancel', 'refund')),
    pending_turn      int,
    last_decision     text,
    last_reason       text,
    action_taken      text,
    created_at        timestamptz NOT NULL DEFAULT now()
);

-- UNIQUE(order_id) is the idempotency guarantee: an order can be refunded once, ever.
CREATE TABLE IF NOT EXISTS refunds (
    refund_id  uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id   text          NOT NULL UNIQUE REFERENCES orders(order_id),
    session_id uuid          NOT NULL,
    amount     numeric(10,2) NOT NULL CHECK (amount >= 0),
    created_at timestamptz   NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS escalations (
    escalation_id uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    uuid        NOT NULL,
    order_id      text        REFERENCES orders(order_id),
    reason        text        NOT NULL,
    status        text        NOT NULL DEFAULT 'open',
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- Audit log: every tool call, who/what/when, success or failure.
CREATE TABLE IF NOT EXISTS actions (
    action_id  bigserial   PRIMARY KEY,
    session_id uuid        NOT NULL,
    tool       text        NOT NULL,
    input      jsonb       NOT NULL,
    result     jsonb       NOT NULL,
    ok         boolean     NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS actions_session_idx ON actions (session_id, action_id);

CREATE TABLE IF NOT EXISTS cases (
    case_id      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   uuid        NOT NULL,
    order_id     text        REFERENCES orders(order_id),
    issue_type   text        NOT NULL,
    action_taken text,
    outcome      text        NOT NULL CHECK (
        outcome IN ('resolved', 'denied', 'escalated', 'verification_failed', 'informational')),
    reason       text        NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS cases_order_idx ON cases (order_id);

CREATE TABLE IF NOT EXISTS messages (
    message_id bigserial   PRIMARY KEY,
    session_id uuid        NOT NULL,
    role       text        NOT NULL CHECK (role IN ('user', 'assistant', 'tool_result')),
    content    jsonb       NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_session_idx ON messages (session_id, message_id);
