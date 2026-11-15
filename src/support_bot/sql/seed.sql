-- Destructive demo reset. Relative dates keep scenarios valid forever.
TRUNCATE messages, cases, actions, escalations, refunds, sessions,
         order_items, orders, customers RESTART IDENTITY CASCADE;

INSERT INTO customers (name, email, phone) VALUES
    ('Maria Lopez',  'maria@example.com',  '+34600111222'),
    ('Jordan Ellis', 'jordan@example.com', '+15551234567'),
    ('Sara Haddad',  'sara@example.com',   '+9715011122');

INSERT INTO orders (order_id, customer_id, status, total_amount, placed_at, delivered_at) VALUES
    ('A1001', (SELECT customer_id FROM customers WHERE email = 'maria@example.com'),
     'processing',  24.00, now() - interval '2 days',  NULL),
    ('A1002', (SELECT customer_id FROM customers WHERE email = 'jordan@example.com'),
     'delivered',   49.00, now() - interval '9 days',  now() - interval '5 days'),
    ('A1003', (SELECT customer_id FROM customers WHERE email = 'maria@example.com'),
     'delivered',   24.00, now() - interval '50 days', now() - interval '45 days'),
    ('A1004', (SELECT customer_id FROM customers WHERE email = 'sara@example.com'),
     'delivered',  249.00, now() - interval '8 days',  now() - interval '3 days');

INSERT INTO order_items (order_id, name, quantity, unit_price) VALUES
    ('A1001', 'Blue Stoneware Mug', 1,  24.00),
    ('A1002', 'Walnut Desk Lamp',   1,  49.00),
    ('A1003', 'Blue Stoneware Mug', 1,  24.00),
    ('A1004', 'Oak Bedside Table',  1, 199.00),
    ('A1004', 'Linen Table Runner', 2,  25.00);
