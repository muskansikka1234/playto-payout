import React from 'react';
import { formatINR, formatDate } from '../utils/format';

const entryStyles = {
  credit:       { color: '#4ade80', sign: '+', label: 'Credit' },
  debit:        { color: '#f87171', sign: '−', label: 'Debit' },
  hold:         { color: '#fbbf24', sign: '−', label: 'Hold' },
  hold_release: { color: '#38bdf8', sign: '+', label: 'Released' },
};

const LedgerTable = ({ ledger }) => {
  const entries = ledger?.entries || [];

  if (entries.length === 0) {
    return (
      <div className="glass-card p-8" style={{ textAlign: 'center' }}>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>No ledger entries.</p>
      </div>
    );
  }

  return (
    <div className="glass-card animate-fade-in" style={{ overflow: 'hidden' }}>
      <div style={{ padding: '20px 24px 16px', borderBottom: '1px solid rgba(51,65,85,0.5)' }}>
        <h3 style={{ fontFamily: 'Syne', fontWeight: 700, fontSize: '1.05rem' }}>
          Ledger
        </h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', marginTop: 4 }}>
          Source of truth — every balance change recorded here
        </p>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid rgba(51,65,85,0.4)' }}>
              {['Type', 'Amount', 'Description', 'Date'].map((h) => (
                <th key={h} style={{
                  padding: '10px 16px',
                  textAlign: 'left',
                  color: 'var(--text-secondary)',
                  fontSize: '0.7rem',
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  fontFamily: 'JetBrains Mono',
                  fontWeight: 500,
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, i) => {
              const style = entryStyles[entry.entry_type] || { color: '#94a3b8', sign: '', label: entry.entry_type };
              const absAmount = Math.abs(entry.amount_paise);
              return (
                <tr
                  key={entry.id}
                  style={{ borderBottom: i < entries.length - 1 ? '1px solid rgba(51,65,85,0.2)' : 'none' }}
                  onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(51,65,85,0.12)'}
                  onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                >
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{
                      background: `${style.color}15`,
                      color: style.color,
                      border: `1px solid ${style.color}30`,
                      padding: '2px 9px',
                      borderRadius: 6,
                      fontSize: '0.7rem',
                      fontFamily: 'JetBrains Mono',
                      fontWeight: 600,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                    }}>
                      {style.label}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{ fontFamily: 'JetBrains Mono', fontWeight: 600, color: style.color }}>
                      {style.sign}{formatINR(absAmount)}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontSize: '0.82rem', maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {entry.description}
                  </td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontSize: '0.78rem', whiteSpace: 'nowrap' }}>
                    {formatDate(entry.created_at)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default LedgerTable;
