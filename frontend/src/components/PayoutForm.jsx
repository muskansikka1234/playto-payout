import React, { useState } from 'react';
import { createPayout } from '../utils/api';
import { generateUUID } from '../utils/format';

const PayoutForm = ({ merchant, onSuccess }) => {
  const [amountINR, setAmountINR] = useState('');
  const [bankAccountId, setBankAccountId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const bankAccounts = merchant?.bank_accounts || [];

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    const amountPaise = Math.round(parseFloat(amountINR) * 100);
    if (!amountINR || isNaN(amountPaise) || amountPaise < 100) {
      setError('Minimum payout is ₹1.00');
      return;
    }
    if (!bankAccountId) {
      setError('Please select a bank account.');
      return;
    }

    const availablePaise = merchant?.available_balance_paise || 0;
    if (amountPaise > availablePaise) {
      setError(`Insufficient balance. Available: ₹${(availablePaise / 100).toFixed(2)}`);
      return;
    }

    setLoading(true);
    try {
      const idempotencyKey = generateUUID();
      await createPayout(merchant.id, idempotencyKey, {
        amount_paise: amountPaise,
        bank_account_id: bankAccountId,
      });
      setSuccess(`Payout of ₹${amountINR} initiated successfully!`);
      setAmountINR('');
      setBankAccountId('');
      if (onSuccess) onSuccess();
    } catch (err) {
      const msg = err.response?.data?.error || err.response?.data?.detail || 'Failed to create payout.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-card p-6 animate-slide-up">
      <h3 style={{ fontFamily: 'Syne', fontWeight: 700, fontSize: '1.1rem', marginBottom: 20, color: 'var(--text-primary)' }}>
        Request Payout
      </h3>

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label style={{ display: 'block', color: 'var(--text-secondary)', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.07em', fontFamily: 'JetBrains Mono', marginBottom: 6 }}>
            Amount (₹)
          </label>
          <input
            type="number"
            placeholder="0.00"
            value={amountINR}
            onChange={(e) => setAmountINR(e.target.value)}
            min="1"
            step="0.01"
          />
        </div>

        <div>
          <label style={{ display: 'block', color: 'var(--text-secondary)', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.07em', fontFamily: 'JetBrains Mono', marginBottom: 6 }}>
            Bank Account
          </label>
          <select value={bankAccountId} onChange={(e) => setBankAccountId(e.target.value)}>
            <option value="">Select account…</option>
            {bankAccounts.map((acc) => (
              <option key={acc.id} value={acc.id}>
                {acc.bank_name} — ****{acc.account_number.slice(-4)}
              </option>
            ))}
          </select>
        </div>

        {error && (
          <div style={{ background: 'rgba(248,113,113,0.1)', border: '1px solid rgba(248,113,113,0.25)', borderRadius: 10, padding: '10px 14px', color: '#f87171', fontSize: '0.85rem' }}>
            {error}
          </div>
        )}
        {success && (
          <div style={{ background: 'rgba(74,222,128,0.1)', border: '1px solid rgba(74,222,128,0.25)', borderRadius: 10, padding: '10px 14px', color: '#4ade80', fontSize: '0.85rem' }}>
            {success}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          style={{
            marginTop: 4,
            padding: '12px',
            borderRadius: 10,
            border: 'none',
            background: loading ? 'rgba(56,189,248,0.3)' : 'var(--accent)',
            color: '#0a0f1e',
            fontWeight: 700,
            fontSize: '0.9rem',
            fontFamily: 'Syne',
            cursor: loading ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            transition: 'background 0.2s',
          }}
        >
          {loading ? (
            <>
              <svg className="spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
              </svg>
              Processing…
            </>
          ) : 'Initiate Payout →'}
        </button>
      </form>
    </div>
  );
};

export default PayoutForm;
