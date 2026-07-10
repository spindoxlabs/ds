<script lang="ts">
  import { onDestroy } from 'svelte';
  import PolicySummary from './PolicySummary.svelte';
  import type { PolicySummary as PolicySummaryType } from '$lib/server/odrl';

  let {
    assetId,
    counterPartyAddress,
    offerId,
    assigner,
    odrlPolicy,
    policySummary,
    onClose,
    onComplete,
  }: {
    assetId: string;
    counterPartyAddress: string;
    offerId: string;
    assigner: string;
    odrlPolicy: Record<string, unknown> | null;
    policySummary: PolicySummaryType | null;
    onClose: () => void;
    onComplete: (result: { agreementId: string; transferId: string }) => void;
  } = $props();

  const purposes = [
    { value: 'ds:purpose:EnergyBalancing', label: 'Energy Community Balancing' },
    { value: 'ds:purpose:GridMonitoring', label: 'Grid Monitoring' },
    { value: 'ds:purpose:UrbanPlanning', label: 'Urban Planning' },
  ];

  // Steps: review → purpose → negotiating → transferring → done
  type Step = 'review' | 'purpose' | 'negotiating' | 'transferring' | 'done';

  let step = $state<Step>('review');
  let selectedPurpose = $state('');
  let acknowledged = $state(false);
  let error = $state<string | null>(null);
  let progressLabel = $state('Contacting provider…');
  let result = $state<{ agreementId: string; transferId: string } | null>(null);

  const POLL_INTERVAL_MS = 2000;
  const NEGOTIATION_TIMEOUT_MS = 120_000;
  const TRANSFER_TIMEOUT_MS = 60_000;

  let pollTimer: ReturnType<typeof setInterval> | null = null;

  onDestroy(() => { if (pollTimer) clearInterval(pollTimer); });

  function clearPoll() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  async function startNegotiation() {
    step = 'negotiating';
    progressLabel = 'Initiating contract negotiation…';
    error = null;

    let negotiationId: string;
    try {
      const res = await fetch('/consumer/negotiate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          counter_party_address: counterPartyAddress,
          offer_id: offerId,
          asset_id: assetId,
          assigner,
          odrl_policy: odrlPolicy,
          purpose: selectedPurpose,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      negotiationId = data.negotiation_id;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to start negotiation';
      step = 'purpose';
      return;
    }

    // Poll negotiation state
    const negotiationStart = Date.now();
    const TERMINAL_NEG = new Set(['FINALIZED', 'TERMINATED']);

    await new Promise<string>((resolve, reject) => {
      pollTimer = setInterval(async () => {
        if (Date.now() - negotiationStart > NEGOTIATION_TIMEOUT_MS) {
          clearPoll();
          reject(new Error('Negotiation timed out — the provider may be slow. Try again later.'));
          return;
        }
        try {
          const res = await fetch(`/consumer/negotiations/${negotiationId}`);
          if (!res.ok) return; // transient — keep polling
          const data = await res.json();
          progressLabel = `Negotiating… (${data.state})`;
          if (data.state === 'FINALIZED') {
            const agreementId = data.agreement_id ?? data.contract_agreement_id ?? data.contractAgreementId;
            if (!agreementId) {
              clearPoll();
              reject(new Error('Negotiation finalized without a contract agreement id'));
              return;
            }
            clearPoll();
            resolve(agreementId);
          } else if (data.state === 'TERMINATED') {
            clearPoll();
            reject(new Error(data.error ?? 'Negotiation terminated by provider'));
          }
        } catch { /* transient network error — keep polling */ }
      }, POLL_INTERVAL_MS);
    }).then(async (agreementId) => {
      await startTransfer(agreementId);
    }).catch((e) => {
      error = e instanceof Error ? e.message : 'Negotiation failed';
      step = 'purpose';
    });
  }

  async function startTransfer(agreementId: string) {
    step = 'transferring';
    progressLabel = 'Starting data transfer…';

    let transferId: string;
    try {
      const res = await fetch('/consumer/transfer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          counter_party_address: counterPartyAddress,
          connector_id: assigner,
          agreement_id: agreementId,
          asset_id: assetId,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      transferId = data.transfer_id;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to start transfer';
      step = 'purpose';
      return;
    }

    const transferStart = Date.now();

    await new Promise<void>((resolve, reject) => {
      pollTimer = setInterval(async () => {
        if (Date.now() - transferStart > TRANSFER_TIMEOUT_MS) {
          clearPoll();
          reject(new Error('Transfer timed out. Check the Transfers panel.'));
          return;
        }
        try {
          const res = await fetch(`/consumer/transfers/${transferId}`);
          if (!res.ok) return;
          const data = await res.json();
          progressLabel = `Provisioning transfer… (${data.state})`;
          if (data.state === 'STARTED') {
            clearPoll();
            resolve();
          } else if (data.state === 'TERMINATED' || data.state === 'COMPLETED') {
            clearPoll();
            reject(new Error(data.error ?? `Transfer ended with state: ${data.state}`));
          }
        } catch { /* transient — keep polling */ }
      }, POLL_INTERVAL_MS);
    }).then(() => {
      result = { agreementId, transferId };
      step = 'done';
      onComplete(result);
    }).catch((e) => {
      error = e instanceof Error ? e.message : 'Transfer failed';
      step = 'purpose';
    });
  }

  const stepLabels: Record<Step, string> = {
    review: 'Step 1 — Review Policy',
    purpose: 'Step 2 — Declare Purpose',
    negotiating: 'Negotiating…',
    transferring: 'Starting Transfer…',
    done: 'Access Granted',
  };
</script>

<!-- Modal backdrop -->
<div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" role="dialog" aria-modal="true">
  <div class="bg-white rounded-2xl shadow-xl w-full max-w-lg">
    <!-- Header -->
    <div class="flex items-center justify-between p-5 border-b border-gray-100">
      <h2 class="text-lg font-semibold text-gray-900">{stepLabels[step]}</h2>
      <button onclick={onClose} class="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
    </div>

    <div class="p-5">
      {#if step === 'review'}
        {#if policySummary}
          <PolicySummary summary={policySummary} />
        {:else}
          <p class="text-gray-500 text-sm">No policy details available for this dataset.</p>
        {/if}
        <label class="flex items-start gap-3 mt-4 cursor-pointer">
          <input type="checkbox" bind:checked={acknowledged} class="mt-0.5" />
          <span class="text-sm text-gray-700">I have read and understood the access policy.</span>
        </label>
        <div class="flex gap-3 mt-5 justify-end">
          <button class="ds-btn-secondary" onclick={onClose}>Cancel</button>
          <button class="ds-btn-primary" disabled={!acknowledged} onclick={() => (step = 'purpose')}>
            Next →
          </button>
        </div>

      {:else if step === 'purpose'}
        <p class="text-sm text-gray-600 mb-4">Select the purpose for which you need this data:</p>
        <select bind:value={selectedPurpose} class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-brand-600 focus:outline-none">
          <option value="">— choose purpose —</option>
          {#each purposes as p}
            <option value={p.value}>{p.label}</option>
          {/each}
        </select>
        {#if error}
          <div class="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg">
            <p class="text-sm text-red-700">{error}</p>
          </div>
        {/if}
        <div class="flex gap-3 mt-5 justify-end">
          <button class="ds-btn-secondary" onclick={() => (step = 'review')}>← Back</button>
          <button class="ds-btn-primary" disabled={!selectedPurpose} onclick={startNegotiation}>
            Request Access
          </button>
        </div>

      {:else if step === 'negotiating' || step === 'transferring'}
        <div class="flex flex-col items-center py-8 gap-5">
          <div class="w-10 h-10 border-4 border-brand-600 border-t-transparent rounded-full animate-spin"></div>
          <div class="text-center space-y-1">
            <p class="text-sm font-medium text-gray-800">{progressLabel}</p>
            <p class="text-xs text-gray-400">
              {step === 'negotiating'
                ? 'Verifying credentials and policy with the provider connector…'
                : 'Provisioning the data transfer endpoint…'}
            </p>
          </div>
          <!-- Step indicators -->
          <div class="flex items-center gap-2 text-xs text-gray-400 mt-2">
            <span class="font-medium {step === 'negotiating' ? 'text-brand-600' : 'text-green-600'}">
              {step === 'negotiating' ? '① Negotiating' : '① Negotiated ✓'}
            </span>
            <span class="text-gray-300">→</span>
            <span class="font-medium {step === 'transferring' ? 'text-brand-600' : 'text-gray-400'}">
              ② Transfer
            </span>
          </div>
        </div>

      {:else if step === 'done' && result}
        <div class="space-y-3">
          <div class="flex items-center gap-3 text-green-700">
            <span class="text-2xl">✓</span>
            <p class="font-medium">Access granted!</p>
          </div>
          <dl class="text-sm space-y-1 bg-gray-50 rounded-lg p-3">
            <div class="flex gap-2">
              <dt class="text-gray-500 w-28 shrink-0">Agreement</dt>
              <dd class="font-mono text-xs text-gray-700 truncate">{result.agreementId}</dd>
            </div>
            <div class="flex gap-2">
              <dt class="text-gray-500 w-28 shrink-0">Transfer</dt>
              <dd class="font-mono text-xs text-gray-700 truncate">{result.transferId}</dd>
            </div>
          </dl>
        </div>
        <div class="flex justify-end mt-5">
          <button class="ds-btn-primary" onclick={onClose}>Done</button>
        </div>
      {/if}
    </div>
  </div>
</div>
