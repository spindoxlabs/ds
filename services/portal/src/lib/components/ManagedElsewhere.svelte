<script lang="ts">
  import { participantLabel, type Custody } from '$lib/subject-problems';

  // Shown instead of the subject pages' content on a portal whose participant
  // does not hold the person's credentials: nothing here can be read or changed
  // for them, and saying so beats a refusal per section.
  let { custody, isProvider = false }: { custody: Custody; isProvider?: boolean } = $props();
</script>

<div class="ds-card border-blue-200 bg-blue-50 text-sm text-blue-900 space-y-2" role="status">
  <p class="font-medium">Your data is managed by {participantLabel(custody.home)}</p>
  <p>
    This is the portal of <strong>{participantLabel(custody.here)}</strong>. Your membership,
    your sharing choices and your consent requests are held by
    <strong>{participantLabel(custody.home)}</strong>, so they cannot be shown or changed
    here. Open the portal of the organisation you joined to manage them.
  </p>
  {#if isProvider}
    <p>
      If you work for {participantLabel(custody.here)}, its own records are under
      <a href="/provider" class="underline">Provider</a>.
    </p>
  {/if}
</div>
