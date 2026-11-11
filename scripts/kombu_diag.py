# -*- coding: utf-8 -*-
from kombu import Connection

for u in ['redis://127.0.0.1:6379/4', 'redis://:@127.0.0.1:6379/4']:
    print("testing URL:", u, flush=True)
    conn = Connection(u, connect_timeout=5, transport_options={'socket_connect_timeout': 5, 'socket_timeout': 5})
    try:
        conn.ensure_connection(max_retries=1)
        print("  connected ok", flush=True)
        sq = conn.SimpleQueue('xgsz_diag_queue')
        sq.put({'hello': 'world'})
        print("  SimpleQueue put ok", flush=True)
        sq.close()
        conn.release()
    except Exception as e:
        print("  ERROR:", repr(e), flush=True)
    print("---", flush=True)
print("DONE", flush=True)
