import React from 'react';
import { formatINR } from '../utils/format';

const BalanceCard = ({ merchant }) => {
  if (!merchant) return null;

  const available = merchant.available_balance_paise || 0;
  const held = merchant.held_balance_paise || 0;
  const total = merchant.total_balance_paise || 0;

  return (
    <div className="glass-card glow-accent p-6 animate-slide-up">
      <div className="flex items-start justify-between mb-6">
        <div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', letterSpacing: '0.08em', textTransform: 'uppercase', fontFamily: 'JetBrains Mono' }}>
            Available Balance
          </p>
          <h2 style={{ fontFamily: 'Syne', fontSize: '2.6rem', fontWeight: 800, color: 'var(--accent)', lineHeight: 1.1, marginTop: 4 }}>
            {formatINR(available)}
          </h2>
        </div>
        <div style={{
          background: 'rgba(56,189,248,0.08)',
          border: '1px solid rgba(56,189,248,0.2)',
          borderRadius: 12,
          padding: '10px 14px',
          textAlign: 'right',
        }}>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.06em', fontFamily: 'JetBrains Mono' }}>
            Total
          </p>
          <p style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: '1rem', fontFamily: 'JetBrains Mono' }}>
            {formatINR(total)}
          </p>
        </div>
      </div>

      {held > 0 && (
        <div style={{
          background: 'rgba(251,191,36,0.06)',
          border: '1px solid rgba(251,191,36,0.15)',
          borderRadius: 10,
          padding: '10px 14px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="pulse-dot" style={{ width: 7, height: 7, borderRadius: '50%', background: '#fbbf24', display: 'inline-block' }} />
            <span style={{ color: '#fbbf24', fontSize: '0.8rem', fontWeight: 500 }}>Funds on hold</span>
          </div>
          <span style={{ color: '#fbbf24', fontFamily: 'JetBrains Mono', fontWeight: 600, fontSize: '0.9rem' }}>
            {formatINR(held)}
          </span>
        </div>
      )}

      <div style={{ marginTop: 20, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <StatPill label="Merchant" value={merchant.name} />
        <StatPill label="Email" value={merchant.email} />
      </div>
    </div>
  );
};

const StatPill = ({ label, value }) => (
  <div style={{
    background: 'rgba(30,41,59,0.6)',
    borderRadius: 10,
    padding: '8px 12px',
  }}>
    <p style={{ color: 'var(--text-secondary)', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.07em', fontFamily: 'JetBrains Mono' }}>
      {label}
    </p>
    <p style={{ color: 'var(--text-primary)', fontSize: '0.85rem', fontWeight: 500, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
      {value}
    </p>
  </div>
);

export default BalanceCard;
