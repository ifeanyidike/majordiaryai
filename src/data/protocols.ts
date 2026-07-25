/** Needling / synchronization protocol tables — mirrors the Phase 1 spec exactly. */

export interface ProtocolStep {
  day: number;
  treatment: string;
  /** Final day of the protocol — the cow moves to Timed Breeding for AI */
  final?: boolean;
}

export interface ProtocolDef {
  value: string;
  label: string;
  steps: ProtocolStep[];
}

export const PROTOCOLS: ProtocolDef[] = [
  {
    value: 'ovsynch',
    label: 'Ovsynch',
    steps: [
      { day: 1, treatment: '2cc GnRH' },
      { day: 7, treatment: '2cc PGF' },
      { day: 10, treatment: '2cc GnRH + Insemination', final: true },
    ],
  },
  {
    value: 'prostaglandin_heat',
    label: 'PGF Heat',
    steps: [
      { day: 1, treatment: '2cc PGF' },
      { day: 3, treatment: 'Heat examination' },
      { day: 4, treatment: 'Heat observation' },
      { day: 5, treatment: 'Heat observation + AI if in heat', final: true },
    ],
  },
  {
    value: 'double_ovsynch',
    label: 'Double Ovsynch',
    steps: [
      { day: 1, treatment: '2cc GnRH' },
      { day: 7, treatment: '2cc PGF' },
      { day: 10, treatment: '2cc GnRH' },
      { day: 17, treatment: '2cc GnRH' },
      { day: 24, treatment: '2cc PGF' },
      { day: 25, treatment: '2cc PGF' },
      { day: 27, treatment: '2cc GnRH + Insemination', final: true },
    ],
  },
  {
    value: 'presynch',
    label: 'Presynch',
    steps: [
      { day: 1, treatment: '2cc PGF' },
      { day: 14, treatment: '2cc PGF' },
      { day: 17, treatment: '2cc GnRH' },
      { day: 24, treatment: '2cc GnRH' },
      { day: 31, treatment: '2cc PGF' },
      { day: 34, treatment: '2cc GnRH + Insemination', final: true },
    ],
  },
  {
    value: 'general_synch',
    label: 'General Synch',
    steps: [
      { day: 1, treatment: '2cc PGF' },
      { day: 12, treatment: '2cc GnRH' },
      { day: 19, treatment: '2cc PGF' },
      { day: 22, treatment: '2cc GnRH + Insemination', final: true },
    ],
  },
  {
    value: 'general_synch_2',
    label: 'General Synch 2',
    steps: [
      { day: 1, treatment: '2cc PGF' },
      { day: 10, treatment: '2cc GnRH' },
      { day: 17, treatment: '2cc PGF' },
      { day: 20, treatment: '2cc GnRH + Insemination', final: true },
    ],
  },
];

export const protocolByValue = (value: string) => PROTOCOLS.find((p) => p.value === value);

/** Per the spec, program entry days should land on Monday, Tuesday or Saturday. */
export function isPreferredStartDay(iso: string): boolean {
  const [y, m, d] = iso.split('-').map(Number);
  const dow = new Date(y, (m ?? 1) - 1, d ?? 1).getDay();
  return dow === 1 || dow === 2 || dow === 6;
}
