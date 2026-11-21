#!/bin/sh
# Adds DEMO_NET_DELAY to every packet this container sends (netem delays egress only, so it adds once per round
# trip), shows the /health round trip before and after, then runs load.py with the given arguments.
set -eu

delay="${DEMO_NET_DELAY:-40ms}"

echo "health round trip without delay: $(python probe.py)"
if tc qdisc replace dev eth0 root netem delay "$delay"; then
  echo "health round trip with ${delay} netem delay: $(python probe.py)"
else
  echo "WARNING: could not add the netem delay (needs NET_ADMIN and the sch_netem kernel module); running without it" >&2
fi

exec python load.py "$@"
