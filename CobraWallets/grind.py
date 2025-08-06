import multiprocessing as mp
import time
import logging
import base58
from solders.keypair import Keypair # type: ignore

from multiprocessing.queues import Queue as MPQueue
from multiprocessing.synchronize import Event as MPEvent
try: from colors import *;
except: from .colors import *;

logging.basicConfig(level=logging.INFO)

class Grinder:
    def __init__(self):
        self.q = mp.Queue()
        self.stop_event = mp.Event()

    def _worker(
        self,
        includes: str,
        stop_event: MPEvent,
        out_q: MPQueue,
    ) -> None:
        time_start = time.time()
        while not stop_event.is_set():
            goes_for = time.time() - time_start
            if goes_for > 60:
                logging.info(f"[-] Grinder timed out after {goes_for:.1f}s")
                break

            kp = Keypair()
            addr = str(kp.pubkey())
            if addr.endswith(includes) or addr.startswith(includes):
                privkey = base58.b58encode(bytes(kp)).decode()
                out_q.put((addr, privkey))
                stop_event.set()
                return

    def grind_custom_wallet(self, includes: str = "CB") -> tuple[str, str] | tuple[None, None]:
        try:
            n_workers = mp.cpu_count() - 1

            logging.info(f"[*] Spinning up {n_workers} workers to grind for ‘...{includes}’")
            start = time.time()

            procs = []
            for _ in range(n_workers):
                p = mp.Process(target=self._worker, args=(includes, self.stop_event, self.q), daemon=True)
                p.start()
                procs.append(p)

            data = self.q.get(timeout=60)
            if data is None:
                logging.info(f"[-] Grinder timed out after {time.time() - start:.1f}s")
                return None, None

            addr, secret = data
            elapsed = time.time() - start

            self.stop_event.set()
            for p in procs:
                p.terminate()
                p.join()

            logging.info(f"[+] Found {addr} in {elapsed:.1f}s")
            return addr, secret

        except Exception as e:
            logging.error(f"[-] Grinder failed: {e}")
            return None, None

    def grind_wallet(self) -> tuple[str, str] | tuple[None, None]:
        try:
            kp = Keypair()
            addr = str(kp.pubkey())
            privkey = base58.b58encode(bytes(kp)).decode()

            logging.info(f"[+] Found {addr}")
            return addr, privkey

        except Exception as e:
            logging.error(f"[-] Grinder failed: {e}")
            return None, None
