-- placeholder golden snippets; tests will assert presence of key lines in CLI run
ALTER TABLE orders RENAME COLUMN total_price TO amount;
ALTER TABLE orders ALTER COLUMN amount TYPE numeric(12,2) USING amount::numeric(12,2);
ALTER TABLE orders ALTER COLUMN amount SET DEFAULT 0;
ALTER TABLE orders ADD CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users (id) NOT VALID;
ALTER TABLE orders VALIDATE CONSTRAINT fk_orders_user;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_orders_status ON orders USING btree (status);


