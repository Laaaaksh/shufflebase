-- Demo dataset for the Shufflebase README/GIF: a small e-commerce-shaped
-- schema with a real foreign key relationship, seeded with obviously-fake
-- but realistic-looking PII so the before/after masking is visible at a
-- glance.

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

INSERT INTO customers (email, full_name, phone) VALUES
    ('maria.garcia@acme-corp.example', 'Maria Garcia', '555-0142'),
    ('james.chen@acme-corp.example',   'James Chen',   '555-0198'),
    ('priya.patel@acme-corp.example',  'Priya Patel',  '555-0177');

INSERT INTO orders (customer_id, total_cents) VALUES
    (1, 4899),
    (1, 1250),
    (2, 9900),
    (3, 3400);
