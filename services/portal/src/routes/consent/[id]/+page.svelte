<script lang="ts">
  import ConsentBadge from '$lib/components/ConsentBadge.svelte';
  import ManagedElsewhere from '$lib/components/ManagedElsewhere.svelte';
  import PolicySummary from '$lib/components/PolicySummary.svelte';
  import ProblemNotice from '$lib/components/ProblemNotice.svelte';
  import TechnicalDetails from '$lib/components/TechnicalDetails.svelte';
  import type { Problem } from '$lib/subject-problems';

  let { data, form } = $props();
  const allProblems = $derived(
    form?.problem ? [...(data.problems as Problem[]), form.problem as Problem] : (data.problems as Problem[]),
  );
  const consent = $derived(data.consent);
</script>

<svelte:head>
  <title>Consent Request</title>
</svelte:head>

<div class="max-w-lg mx-auto space-y-5">
  <a href="/consent" class="text-sm text-brand-600 hover:underline">← Back to My Consents</a>

  {#if form?.problem}
    <ProblemNotice problem={form.problem} />
  {/if}

  {#if !data.custody.isHome}
    <ManagedElsewhere custody={data.custody} isProvider={data.persona?.isProvider} />
  {:else if data.problems.length}
    {#each data.problems as problem}
      <ProblemNotice {problem} />
    {/each}
  {:else if !consent}
    <div class="ds-card text-sm text-gray-600">This consent request was not found.</div>
  {:else}
    <div class="ds-card space-y-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <p class="text-xs text-gray-500 uppercase tracking-wide mb-1">Request from</p>
          <h1 class="text-xl font-bold text-gray-900">{consent.consumer_id}</h1>
        </div>
        <ConsentBadge status={consent.status} />
      </div>

      <div class="border-t border-gray-100 pt-4 space-y-3">
        <div>
          <p class="text-sm font-medium text-gray-700">They want access to:</p>
          <p class="text-base text-gray-900 mt-1">📊 {consent.dataset_id}</p>
        </div>

        {#if consent.purpose?.length}
          <div>
            <p class="text-sm font-medium text-gray-700">Declared purpose:</p>
            <ul class="mt-1 space-y-1">
              {#each consent.purpose as p}
                <li class="text-sm text-gray-800">{p.split(':').pop()?.replace(/([A-Z])/g, ' $1').trim()}</li>
              {/each}
            </ul>
          </div>
        {/if}

        {#if consent.message}
          <div>
            <p class="text-sm font-medium text-gray-700">Why they say they need it:</p>
            <p class="mt-1 text-sm text-gray-600 italic">"{consent.message}"</p>
          </div>
        {/if}

        {#if data.policySummary}
          <div class="border-t border-gray-100 pt-3">
            <p class="text-sm font-medium text-gray-700 mb-2">Access policy:</p>
            <PolicySummary summary={data.policySummary} />
          </div>
        {/if}

        <p class="text-sm text-gray-500">
          You can revoke this consent at any time from your dashboard.
        </p>
      </div>
    </div>

    <!-- Actions -->
    {#if consent.status === 'pending'}
      <div class="flex gap-3">
        <form method="POST" action="?/approve" class="flex-1">
          <button type="submit" class="ds-btn-primary w-full">Approve</button>
        </form>
        <form method="POST" action="?/reject" class="flex-1">
          <button type="submit" class="ds-btn-danger w-full">Reject</button>
        </form>
      </div>
    {:else if consent.status === 'granted'}
      <form method="POST" action="?/revoke">
        <button type="submit" class="ds-btn-danger w-full">Revoke consent</button>
      </form>
    {:else}
      <p class="text-center text-sm text-gray-500">This consent request is {consent.status}.</p>
    {/if}
  {/if}

  <TechnicalDetails
    problems={allProblems}
    facts={[
      { label: 'Your identity', value: data.subjectId },
      { label: 'Request id', value: consent?.id ?? null },
      { label: 'This portal’s participant', value: data.custody.here },
      { label: 'Your data is held by', value: data.custody.home },
    ]}
  />
</div>
