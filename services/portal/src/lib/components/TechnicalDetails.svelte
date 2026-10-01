<script lang="ts">
  import { sectionLabel, type Problem } from '$lib/subject-problems';

  // Everything a person does not need but whoever runs the deployment does:
  // identifiers and the backends' own words. Collapsed, at the bottom.
  let {
    problems = [],
    facts = [],
  }: { problems?: Problem[]; facts?: { label: string; value: string | null }[] } = $props();

  const shownFacts = $derived(facts.filter((f) => f.value));
</script>

<details id="technical" class="ds-card text-xs text-gray-600">
  <summary class="cursor-pointer text-sm font-medium text-gray-700">
    Technical details{#if problems.length}
      <span class="ml-1 text-gray-500">({problems.length} issue{problems.length !== 1 ? 's' : ''})</span>{/if}
  </summary>

  {#if shownFacts.length}
    <dl class="mt-3 space-y-1">
      {#each shownFacts as fact}
        <div>
          <dt class="inline text-gray-500">{fact.label}:</dt>
          <dd class="inline"><code class="break-all">{fact.value}</code></dd>
        </div>
      {/each}
    </dl>
  {/if}

  {#each problems as p}
    <div class="mt-3">
      <p class="font-medium text-gray-700">{sectionLabel(p.section)} — {p.title}</p>
      <pre class="mt-1 overflow-x-auto whitespace-pre-wrap break-all rounded bg-gray-50 p-2 font-mono">{p.technical}</pre>
    </div>
  {/each}
</details>
