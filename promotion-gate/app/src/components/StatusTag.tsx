import { CircleCheck, CircleSlash, LoaderCircle, OctagonX, TriangleAlert } from 'lucide-react';
import type { Status } from '../lib/types';

const LABEL: Record<Status | 'RUN', string> = { PASS: 'Apto', WARN: 'Observaciones', FAIL: 'No apto', SKIP: 'Omitido', RUN: 'En curso' };
const ICON = { PASS: CircleCheck, WARN: TriangleAlert, FAIL: OctagonX, SKIP: CircleSlash, RUN: LoaderCircle };

/** Estado siempre con icono y texto: nunca solo color. */
export function StatusTag({ status, label }: { status: Status | 'RUN'; label?: string }) {
  const Icon = ICON[status];
  return (
    <span className={`tag tag--${status}`}>
      <Icon aria-hidden strokeWidth={2.4} />
      {label ?? LABEL[status]}
    </span>
  );
}

export function statusWord(s: Status | 'RUN') {
  return LABEL[s];
}
