import React from 'react';

const MerchantSelector = ({ merchants, selectedId, onSelect }) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <p style={{
        color: 'var(--text-secondary)',
        fontSize: '0.7rem',
        textTransform: 'uppercase',
        letterSpacing: '0.1em',
        fontFamily: 'JetBrains Mono',
        padding: '0 4px',
        marginBottom: 4,
      }}>
        Merchants
      </p>
      {merchants.map((m) => {
        const isSelected = m.id === selectedId;
        const available = m.available_balance_paise || 0;
        return (
          <button
            key={m.id}
            onClick={() => onSelect(m.id)}
            style={{
              background: isSelected ? 'rgba(56,189,248,0.1)' : 'rgba(15,23,42,0.6)',
              border: isSelected ? '1px solid rgba(56,189,248,0.35)' : '1px solid rgba(51,65,85,0.5)',
              borderRadius: 12,
              padding: '12px 14px',
              cursor: 'pointer',
              textAlign: 'left',
              transition: 'all 0.2s',
              width: '100%',
            }}
            onMouseEnter={(e) => { if (!isSelected) e.currentTarget.style.borderColor = 'rgba(56,189,248,0.2)'; }}
            onMouseLeave={(e) => { if (!isSelected) e.currentTarget.style.borderColor = 'rgba(51,65,85,0.5)'; }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{
                width: 34,
                height: 34,
                borderRadius: 10,
                background: isSelected ? 'rgba(56,189,248,0.2)' : 'rgba(51,65,85,0.5)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontFamily: 'Syne',
                fontWeight: 800,
                fontSize: '1rem',
                color: isSelected ? 'var(--accent)' : 'var(--text-secondary)',
                flexShrink: 0,
              }}>
                {m.name.charAt(0)}
              </div>
              <div style={{ overflow: 'hidden' }}>
                <p style={{
                  color: isSelected ? 'var(--accent)' : 'var(--text-primary)',
                  fontWeight: 600,
                  fontSize: '0.88rem',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}>
                  {m.name}
                </p>
                <p style={{
                  color: 'var(--text-secondary)',
                  fontSize: '0.75rem',
                  fontFamily: 'JetBrains Mono',
                  marginTop: 1,
                }}>
                  ₹{(available / 100).toFixed(2)}
                </p>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
};

export default MerchantSelector;
