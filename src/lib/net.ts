import * as Network from 'expo-network';
import { create } from 'zustand';

/**
 * The phone's connection (offline mode, Josh's Part A platform tests).
 *
 * online — false only when the phone has no connection at all. This drives
 * the "No signal" bar, the Sync button and whether saves are sent.
 *
 * Android's "internet reachable" (its own check against Google) is not used.
 * It comes seconds after a reconnect, and never on networks that block that
 * check (some farm Wi-Fi, some VPNs), so the bar said "No signal" while the
 * app was loading and syncing fine. A request that cannot get through fails
 * on its own with a plain "No signal" message, and a save waits.
 */
interface NetState {
  online: boolean;
}

export const useNet = create<NetState>(() => ({ online: true }));

function apply(state: Network.NetworkState) {
  const online = state.isConnected !== false;
  if (online !== useNet.getState().online) useNet.setState({ online });
}

/** Start following the connection. Returns the stop function. */
export function watchNetwork(): () => void {
  Network.getNetworkStateAsync().then(apply).catch(() => {});
  const sub = Network.addNetworkStateListener(apply);
  return () => sub.remove();
}

/** Whether to attempt a request at all. */
export const canTry = () => useNet.getState().online;

/** Call `then` each time the connection comes back. Returns the stop function. */
export function onReconnect(then: () => void): () => void {
  return useNet.subscribe((s, prev) => {
    if (s.online && !prev.online) then();
  });
}
