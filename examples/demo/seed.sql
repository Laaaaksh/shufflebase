-- Demo dataset for the Shufflebase README/GIF: a small e-commerce-shaped
-- schema with real foreign key relationships (customers -> orders ->
-- order_items), seeded with obviously-fake but realistic-looking PII so the
-- before/after masking is visible at a glance.

DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    phone TEXT
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    total_cents INTEGER NOT NULL
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_cents INTEGER NOT NULL
);

INSERT INTO customers (email, full_name, phone) VALUES
    ('maria.garcia@acme-corp.example', 'Maria Garcia', '555-0142'),
    ('james.chen@acme-corp.example',   'James Chen',   '555-0198'),
    ('priya.patel@acme-corp.example',  'Priya Patel',  '555-0177');

INSERT INTO orders (customer_id, total_cents) VALUES
    (1, 4899),
    (1, 1250),
    (2, 9900),
    (3, 3400);

INSERT INTO order_items (order_id, product_name, quantity, unit_price_cents) VALUES
    (1, 'Wireless Mouse',       1, 2899),
    (1, 'USB-C Cable',          2, 1000),
    (2, 'Notebook (A5)',        5, 250),
    (3, 'Mechanical Keyboard',  1, 9900),
    (4, 'Desk Lamp',            1, 3400);
