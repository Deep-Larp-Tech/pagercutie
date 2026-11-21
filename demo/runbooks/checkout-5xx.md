# Checkout answers 5xx

See the [PagerCutie dashboard](http://localhost:3000) for error rates per service.

1. Check which path fails: {{ payload.method }} {{ payload.path }} on {{ payload.service }}.
2. Look at the last deploy of {{ payload.service }}. If it went out in the last hour, roll it back:

   ```sh
   deployctl rollback {{ payload.service }}
   ```

3. Check the payment provider's [status page](https://status.example.com) and the database connection pool.
   Restart the pool only if it is saturated.
- [ ] Post a status update in #checkout-incidents.
- [ ] Resolve the alert once the error rate is back under 1%.
