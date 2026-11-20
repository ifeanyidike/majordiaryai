import * as Network from 'expo-network';
import { create } from 'zustand';

/**
 * The phone's connection (offline mode, Josh's Part A platform tests).
 *
 *   online   — shown to the person: false when the phone says there is no
 *              connection, or that the internet cannot be reached.
 *   canTry   — whether to attempt a request at all: false only when there
 *              is no connection whatever. "Internet unreachable" is not
 *              trusted for this: Android says it on networks where only its
 *              own check is blocked (some farm Wi-Fi), and saves would then
 *              wait forever on a line that works. A request that cannot get
 *              through fails on its own, and the save waits then.
 */
interface NetState {
  online: boolean;
  canTry: boolean;
}

export const useNet = create<NetState>(() => ({ online: true, canTry: true }));

function apply(state: Network.NetworkState) {
  const canTry = state.isConnected !== false;
  const online = canTry && state.isInternetReachable !== false;
  const now = useNet.getState();
  if (online !== now.online || canTry !== now.canTry) useNet.setState({ online, canTry });
}

/** Start following the connection. Returns the stop function. */
export function watchNetwork(): () => void {
  Network.getNetworkStateAsync().then(apply).catch(() => {});
  const sub = Network.addNetworkStateListener(apply);
  return () => sub.remove();
}

export const canTry = () => useNet.getState().canTry;
