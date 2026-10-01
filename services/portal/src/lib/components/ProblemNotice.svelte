<script lang="ts">
  import type { Problem } from '$lib/subject-problems';

  // The sentence a person can act on. The raw error is not shown here — it is
  // in the page's "Technical details" block, which this links to.
  let { problem }: { problem: Problem } = $props();

  const tones: Record<Problem['tone'], string> = {
    info: 'border-blue-200 bg-blue-50 text-blue-900',
    warning: 'border-amber-200 bg-amber-50 text-amber-900',
    error: 'border-red-200 bg-red-50 text-red-800',
  };
</script>

<div class="ds-card text-sm {tones[problem.tone]}" role={problem.tone === 'info' ? 'status' : 'alert'}>
  <p class="font-medium">{problem.title}</p>
  <p class="mt-1">{problem.message}</p>
  <a href="#technical" class="mt-2 inline-block text-xs underline opacity-75 hover:opacity-100">
    Technical details
  </a>
</div>
