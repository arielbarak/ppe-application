/**
 * IndexedDB-backed persistence for the responder's ECDSA key pair.
 *
 * The generateKeyPair() call marks keys as extractable, which makes them
 * structured-cloneable and therefore storable directly in IndexedDB. Persisting
 * the pair lets the same node identity survive a page refresh without forcing
 * the responder to re-register and redo their PPE challenges.
 *
 * All failures are swallowed (logged + null/no-op) so a malfunctioning
 * IndexedDB layer never blocks the in-memory key flow.
 */

const DB_NAME = 'ppe-keystore';
const DB_VERSION = 1;
const STORE_NAME = 'keys';
const KEY_ID = 'responder-keypair';

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function runTx<T>(
  mode: IDBTransactionMode,
  op: (store: IDBObjectStore) => IDBRequest<T>
): Promise<T> {
  return openDb().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, mode);
        const store = tx.objectStore(STORE_NAME);
        const req = op(store);
        req.onsuccess = () => {
          db.close();
          resolve(req.result as T);
        };
        req.onerror = () => {
          db.close();
          reject(req.error);
        };
      })
  );
}

export async function loadKeyPair(): Promise<CryptoKeyPair | null> {
  try {
    const stored = await runTx<CryptoKeyPair | undefined>('readonly', (s) =>
      s.get(KEY_ID) as IDBRequest<CryptoKeyPair | undefined>
    );
    return stored ?? null;
  } catch (e) {
    console.warn('keystore.load failed', e);
    return null;
  }
}

export async function saveKeyPair(keyPair: CryptoKeyPair): Promise<void> {
  try {
    await runTx('readwrite', (s) => s.put(keyPair, KEY_ID));
  } catch (e) {
    console.warn('keystore.save failed', e);
  }
}

export async function clearKeyPair(): Promise<void> {
  try {
    await runTx('readwrite', (s) => s.delete(KEY_ID));
  } catch (e) {
    console.warn('keystore.clear failed', e);
  }
}
