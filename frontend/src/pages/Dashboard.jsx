import React, { useState, useEffect, useCallback } from 'react';
import { getMerchants, getMerchant, getLedger, getPayouts } from '../utils/api';
import BalanceCard from '../components/BalanceCard';
import PayoutForm from '../components/PayoutForm';
import PayoutTable from '../components/PayoutTable';
import LedgerTable from '../components/LedgerTable';
import MerchantSelector from '../components/MerchantSelector';

const TAB_PAYOUTS = 'payouts';
const TAB_LEDGER = 'ledger';

const Dashboard = () => {
  const [merchants, setMerchants] = useState([]);
  const [selectedMerchantId, setSelectedMerchantId] = useState(null);
  const [merchant, setMerchant] = useState(null);
  const [payouts, setPayouts] = useState([]);
  const [ledger, setLedger] = useState(null);
  const [tab, setTab] = useState(TAB_PAYOUTS);
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Load merchant list on mount
  useEffect(() => {
    getMerchants()
      .then((res) => {
        setMerchants(res.data);
        if (res.data.length > 0) setSelectedMerchantId(res.data[0].id);
      })
      .catch(console.error);
  }, []);

  // Load selected merchant data
  const loadMerchantData = useCallback(async (id) => {
    if (!id) return;
    setLoading(true);
    try {
      const [merchantRes, payoutsRes, ledgerRes] = await Promise.all([
        getMerchant(id),
        getPayouts(id),
        getLedger(id),
      ]);
      setMerchant(merchantRes.data);
      setPayouts(payoutsRes.data);
      setLedger(ledgerRes.data);
      // Update merchants list with fresh balance
      setMerchants((prev) =>
        prev.map((m) => (m.id === id ? { ...m, ...merchantRes.data } : m))
      );
    } catch (err) {
      console.error('Failed to load merchant data', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMerchantData(selectedMerchantId);
  }, [selectedMerchantId, loadMerchantData]);

  // Auto-refresh balance every 5s if any payout is in non-terminal state
  useEffect(() => {
    const hasActive = payouts.some(
      (p) => p.status === 'pending' || p.status === 'processing'
    );
    if (!hasActive || !selectedMerchantId) return;

    const interval = setInterval(() => {
      loadMerchantData(selectedMerchantId);
    }, 5000);

    return () => clearInterval(interval);
  }, [payouts, selectedMerchantId, loadMerchantData]);

  const handleStatusUpdate = useCallback((updatedPayout) => {
    setPayouts((prev) =>
      prev.map((p) => (p.id === updatedPayout.id ? updatedPayout : p))
    );
    // Refresh balance when a payout settles
    if (updatedPayout.status === 'completed' || updatedPayout.status === 'failed') {
      loadMerchantData(selectedMerchantId);
    }
  }, [selectedMerchantId, loadMerchantData]);

  const handlePayoutSuccess = () => {
    loadMerchantData(selectedMerchantId);
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg-0)' }}>
      {/* Sidebar */}
      <aside style={{
        width: sidebarOpen ? 240 : 0,
        minWidth: sidebarOpen ? 240 : 0,
        overflow: 'hidden',
        transition: 'width 0.3s, min-width 0.3s',
        borderRight: '1px solid rgba(51,65,85,0.4)',
        background: 'rgba(10,15,30,0.95)',
        padding: sidebarOpen ? '28px 16px' : 0,
        display: 'flex',
        flexDirection: 'column',
        gap: 28,
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingLeft: 4 }}>
          <div style={{
            width: 32,
            height: 32,
            borderRadius: 9,
            background: 'var(--accent)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#0a0f1e" strokeWidth="2.5">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5M2 12l10 5 10-5" />
            </svg>
          </div>
          <span style={{ fontFamily: 'Syne', fontWeight: 800, fontSize: '1.1rem', color: 'var(--text-primary)' }}>
            Playto Pay
          </span>
        </div>

        <MerchantSelector
          merchants={merchants}
          selectedId={selectedMerchantId}
          onSelect={(id) => {
            setSelectedMerchantId(id);
            setMerchant(null);
            setPayouts([]);
            setLedger(null);
          }}
        />
      </aside>

      {/* Main */}
      <main style={{ flex: 1, overflowY: 'auto', padding: '28px 32px' }}>
        {/* Top bar */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <button
              onClick={() => setSidebarOpen((v) => !v)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', padding: 4 }}
              title="Toggle sidebar"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>
            <div>
              <h1 style={{ fontFamily: 'Syne', fontWeight: 800, fontSize: '1.5rem', lineHeight: 1 }}>
                {merchant?.name || 'Payout Dashboard'}
              </h1>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', marginTop: 3 }}>
                Payout Engine — Playto Pay
              </p>
            </div>
          </div>

          <button
            onClick={() => loadMerchantData(selectedMerchantId)}
            style={{
              background: 'rgba(51,65,85,0.4)',
              border: '1px solid rgba(51,65,85,0.6)',
              borderRadius: 10,
              padding: '8px 14px',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              fontSize: '0.8rem',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <svg className={loading ? 'spin' : ''} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M23 4v6h-6M1 20v-6h6" /><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
            </svg>
            Refresh
          </button>
        </div>

        {!selectedMerchantId && (
          <div className="glass-card p-12" style={{ textAlign: 'center' }}>
            <p style={{ color: 'var(--text-secondary)' }}>Select a merchant to view their dashboard.</p>
          </div>
        )}

        {selectedMerchantId && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 20 }}>
            {/* Left column */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
              <BalanceCard merchant={merchant} />

              {/* Tab switcher */}
              <div style={{ display: 'flex', gap: 4, background: 'rgba(15,23,42,0.6)', padding: 4, borderRadius: 12, width: 'fit-content', border: '1px solid rgba(51,65,85,0.4)' }}>
                {[TAB_PAYOUTS, TAB_LEDGER].map((t) => (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    style={{
                      padding: '7px 18px',
                      borderRadius: 9,
                      border: 'none',
                      background: tab === t ? 'var(--accent)' : 'transparent',
                      color: tab === t ? '#0a0f1e' : 'var(--text-secondary)',
                      fontWeight: tab === t ? 700 : 400,
                      fontSize: '0.83rem',
                      cursor: 'pointer',
                      fontFamily: 'DM Sans',
                      transition: 'all 0.2s',
                      textTransform: 'capitalize',
                    }}
                  >
                    {t}
                  </button>
                ))}
              </div>

              {tab === TAB_PAYOUTS && (
                <PayoutTable
                  payouts={payouts}
                  onStatusUpdate={handleStatusUpdate}
                />
              )}
              {tab === TAB_LEDGER && (
                <LedgerTable ledger={ledger} />
              )}
            </div>

            {/* Right column */}
            <div>
              <PayoutForm merchant={merchant} onSuccess={handlePayoutSuccess} />
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default Dashboard;
