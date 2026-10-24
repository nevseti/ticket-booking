-- Проверка целостности после нагрузочного теста.
--   psql -v event=<uuid> -f verify.sql
-- Каждая строка — инвариант: ok = true, если он выполняется. Ненулевой код выхода при
-- нарушении даёт \gset + проверка в конце.

\set ON_ERROR_STOP on

WITH
  e AS (SELECT CAST(:'event' AS uuid) AS id),
  tickets AS (SELECT t.* FROM orders.tickets t, e WHERE t.event_id = e.id),
  orders_ AS (SELECT o.* FROM orders.orders o, e WHERE o.event_id = e.id),
  checkouts AS (SELECT c.* FROM orders.checkouts c, e WHERE c.event_id = e.id),
  sold AS (SELECT s.* FROM booking.sold_seats s, e WHERE s.event_id = e.id),
  holds AS (SELECT h.* FROM booking.holds h, e WHERE h.event_id = e.id),
  payments AS (
    SELECT p.* FROM orders.mock_payments p
    WHERE p.idempotency_key IN (SELECT id::text FROM checkouts)
  ),
  checks(n, name, value, expected) AS (
    VALUES
      (1, 'Места, проданные дважды (билеты на одно место)',
          (SELECT count(*) FROM (SELECT seat_id FROM tickets GROUP BY seat_id HAVING count(*) > 1) d), 0::bigint),
      (2, 'Билеты без проданного места',
          (SELECT count(*) FROM tickets t WHERE NOT EXISTS (
              SELECT 1 FROM sold s WHERE s.seat_id = t.seat_id AND s.order_id = t.order_id)), 0),
      (3, 'Проданные места без билета',
          (SELECT count(*) FROM sold s WHERE NOT EXISTS (
              SELECT 1 FROM tickets t WHERE t.seat_id = s.seat_id AND t.order_id = s.order_id)), 0),
      (4, 'Активные удержания на проданных местах',
          (SELECT count(*) FROM holds h JOIN sold s USING (seat_id)
           WHERE h.status = 'active' AND h.expires_at > now()), 0),
      (5, 'Места с двумя активными удержаниями',
          (SELECT count(*) FROM (SELECT seat_id FROM holds WHERE status = 'active'
                                 GROUP BY seat_id HAVING count(*) > 1) d), 0),
      (6, 'Сумма заказов ≠ сумма билетов (копейки)',
          (SELECT coalesce(sum(o.total_kopecks), 0) - (SELECT coalesce(sum(price_kopecks), 0) FROM tickets)
           FROM orders_ o), 0),
      (7, 'Сумма заказов ≠ сумма списанных платежей (копейки)',
          (SELECT coalesce(sum(total_kopecks), 0) FROM orders_)
            - (SELECT coalesce(sum(amount_kopecks), 0) FROM payments WHERE status = 'succeeded'), 0),
      (8, 'Завершённые саги без заказа',
          (SELECT count(*) FROM checkouts c WHERE c.state = 'completed'
             AND NOT EXISTS (SELECT 1 FROM orders_ o WHERE o.checkout_id = c.id)), 0),
      (9, 'Неуспешные саги, по которым деньги остались списаны',
          (SELECT count(*) FROM checkouts c JOIN payments p ON p.idempotency_key = c.id::text
           WHERE c.state = 'failed' AND p.status = 'succeeded'), 0),
      (10, 'Саги, зависшие в промежуточном состоянии',
          (SELECT count(*) FROM checkouts WHERE state IN ('started', 'paid')), 0)
  )
SELECT n AS "№", name AS "Инвариант", value AS "Значение", value = expected AS ok
FROM checks ORDER BY n;

-- Итоги прогона (для отчёта)
WITH e AS (SELECT CAST(:'event' AS uuid) AS id)
SELECT
  (SELECT count(*) FROM booking.sold_seats s, e WHERE s.event_id = e.id) AS "продано мест",
  (SELECT count(*) FROM orders.orders o, e WHERE o.event_id = e.id) AS "заказов",
  (SELECT count(*) FROM orders.checkouts c, e WHERE c.event_id = e.id AND c.state = 'completed') AS "саг completed",
  (SELECT count(*) FROM orders.checkouts c, e WHERE c.event_id = e.id AND c.state = 'failed') AS "саг failed",
  (SELECT count(*) FROM booking.holds h, e WHERE h.event_id = e.id) AS "удержаний всего",
  (SELECT coalesce(sum(total_kopecks), 0) / 100 FROM orders.orders o, e WHERE o.event_id = e.id) AS "выручка, ₽";
