<script lang="ts">
  import { page } from '$app/stores';

  // A missing permission is the most common way to land here, and it is the case
  // where "something went wrong" is least useful: the user needs to know which
  // grant is missing so they can ask for it.
  const isForbidden = $derived($page.status === 403);
  const title = $derived(
    isForbidden ? 'You do not have access to this page' : `Error ${$page.status}`,
  );
</script>

<svelte:head><title>{title}</title></svelte:head>

<div class="max-w-xl mx-auto py-12 space-y-4">
  <h1 class="text-xl font-bold text-gray-900">{title}</h1>

  <div class="ds-card {isForbidden ? 'border-amber-200 bg-amber-50' : 'border-red-200 bg-red-50'}">
    <p class="text-sm {isForbidden ? 'text-amber-900' : 'text-red-800'}">
      {$page.error?.message ?? 'Something went wrong.'}
    </p>
  </div>

  {#if isForbidden}
    <p class="text-sm text-gray-600">
      Authority comes from two places: Keycloak roles and groups decide operator and
      provider access, while a verifiable credential decides consumer and data-subject
      access. Sections you do hold appear in the navigation above.
    </p>
  {/if}

  <a href="/" class="ds-btn-secondary inline-block text-sm">Back to the catalogue</a>
</div>
