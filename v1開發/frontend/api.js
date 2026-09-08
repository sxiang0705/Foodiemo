export async function getJSON(path, signal) {
  const timeout = AbortSignal.timeout(15000);
  const response = await fetch(path, {
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    headers: {Accept: 'application/json'}, cache: 'no-store'
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.message || '載入失敗，請稍後重試');
  }
  return response.json();
}

export function errorMessage(error) {
  if (error.name === 'TimeoutError') return '連線逾時，請檢查網路後重試';
  if (error instanceof TypeError) return '無法連線，請檢查網路後重試';
  return error.message || '載入失敗，請稍後重試';
}
