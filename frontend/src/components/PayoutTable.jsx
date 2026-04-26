import React, { useEffect, useRef } from 'react';
import { getPayoutStatus } from '../utils/api';
import { formatINR, formatDate } from '../utils/format';

const StatusBadge = ({ status }) => {
  const dot = {
    pending: '#fbbf24',
    processing: '#38bdf8',
    completed: '#4ade80',
    failed: '#f87171',
  }[status] || '#94a3b8';

  return (
    <span className={`status-badge status-${status}`}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: dot, display: 'inline-block' }} />
      {status}
    </span>
  );
};

const PayoutTable = ({ payouts, onStatusUpdate }) => {
  const pollingRefs = useRef({});

  // Live-poll payouts in non-terminal states
  useEffect(() => {
    const activePayouts = payouts.filter(
      (p) => p.status === 'pending' || p.status === 'processing'
    );

    activePayouts.forEach((payout) => {
      if (pollingRefs.current[payout.id]) return; // already polling

      const interval = setInterval(async () => {
        try {
          const res = await getPayoutStatus(payout.id);
          const updated = res.data;
          if (updated.status !== payout.status) {
            onStatusUpdate(updated);
          }
          if (updated.status === 'completed' || updated.status === 'failed') {
            clearInterval(pollingRefs.current[payout.id]);
            delete pollingRefs.current[payout.id];
          }
        } catch (err) {
          // ignore
        }
      }, 2000);

      pollingRefs.current[payout.id] = interval;
    });

    return () => {
      Object.values(pollingRefs.current).forEach(clearInterval);
      pollingRefs.current = {};
    };
  }, [payouts, onStatusUpdate]);

  if (!payouts || payouts.length === 0) {
    return (
      <div className="glass-card p-8" style={{ textAlign: 'center' }}>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>No payouts yet.</p>
      </div>
    );
  }

  return (
    <div className="glass-card animate-fade-in" style={{ overflow: 'hidden' }}>
      <div style={{ padding: '20px 24px 16px', borderBottom: '1px solid rgba(51,65,85,0.5)' }}>
        <h3 style={{ fontFamily: 'Syne', fontWeight: 700, fontSize: '1.05rem' }}>
          Payout History
        </h3>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid rgba(51,65,85,0.4)' }}>
              {['Amount', 'Status', 'Bank', 'Retries', 'Created'].map((h) => (
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
            {payouts.map((payout, i) => (
              <tr
                key={payout.id}
                style={{
                  borderBottom: i < payouts.length - 1 ? '1px solid rgba(51,65,85,0.25)' : 'none',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(51,65,85,0.15)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
              >
                <td style={{ padding: '14px 16px' }}>
                  <span style={{ fontFamily: 'JetBrains Mono', fontWeight: 600, color: 'var(--text-primary)' }}>
                    {formatINR(payout.amount_paise)}
                  </span>
                </td>
                <td style={{ padding: '14px 16px' }}>
                  <StatusBadge status={payout.status} />
                  {payout.failure_reason && (
                    <p style={{ color: '#f87171', fontSize: '0.7rem', marginTop: 3 }}>
                      {payout.failure_reason}
                    </p>
                  )}
                </td>
                <td style={{ padding: '14px 16px', color: 'var(--text-secondary)', fontSize: '0.82rem' }}>
                  {payout.bank_account
                    ? `${payout.bank_account.bank_name} ****${payout.bank_account.account_number?.slice(-4)}`
                    : '—'}
                </td>
                <td style={{ padding: '14px 16px', textAlign: 'center' }}>
                  <span style={{
                    fontFamily: 'JetBrains Mono',
                    fontSize: '0.82rem',
                    color: payout.retry_count > 0 ? '#fbbf24' : 'var(--text-secondary)',
                  }}>
                    {payout.retry_count}
                  </span>
                </td>
                <td style={{ padding: '14px 16px', color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                  {formatDate(payout.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default PayoutTable;
