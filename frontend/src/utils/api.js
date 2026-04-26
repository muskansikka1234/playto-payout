import axios from 'axios';

const BASE_URL = process.env.REACT_APP_API_URL || '/api/v1';

const api = axios.create({ baseURL: BASE_URL });

export const getMerchants = () => api.get('/merchants/');

export const getMerchant = (merchantId) => api.get(`/merchants/${merchantId}/`);

export const getLedger = (merchantId) =>
  api.get(`/merchants/${merchantId}/ledger/`);

export const getPayouts = (merchantId) =>
  api.get('/payouts/list/', {
    headers: { 'X-Merchant-ID': merchantId },
  });

export const createPayout = (merchantId, idempotencyKey, data) =>
  api.post('/payouts/', data, {
    headers: {
      'X-Merchant-ID': merchantId,
      'X-Idempotency-Key': idempotencyKey,
    },
  });

export const getPayoutStatus = (payoutId) => api.get(`/payouts/${payoutId}/`);

export default api;
