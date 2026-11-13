CREATE TABLE IF NOT EXISTS demo_products (
    id INTEGER PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    price NUMERIC(8, 2) NOT NULL
);

INSERT INTO demo_products (id, name, price) VALUES
    (1, 'Keyboard', 25.00),
    (2, 'Mouse', 12.50),
    (3, 'Monitor', 180.00)
ON CONFLICT (id) DO NOTHING;
