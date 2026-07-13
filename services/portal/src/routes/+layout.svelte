<script lang="ts">
  import '../app.css';
  import { page } from '$app/stores';
  import { derivePersona } from '$lib/stores/session';

  let { data, children } = $props();
  const persona = $derived(derivePersona(data.session));
  const isDataSubject = $derived(data.userVcRole === 'DataSubject');
  const isConsumerUser = $derived(data.userVcRole === 'ConsumerUser');

  const navItems = $derived([
    { href: '/', label: 'Catalog', show: isConsumerUser || persona.isAdmin },
    { href: '/my-data', label: 'My Data', show: isDataSubject },
    { href: '/consent', label: 'My Consents', show: isDataSubject },
    { href: '/provider', label: 'Provider', show: persona.isProvider },
    { href: '/consumer', label: 'Consumer', show: isConsumerUser || persona.isAdmin },
    { href: '/admin', label: 'Admin', show: persona.isAdmin },
  ].filter((n) => n.show));

  let mobileOpen = $state(false);
</script>

<div class="min-h-screen flex flex-col">
  <!-- Top nav -->
  <header class="bg-brand-700 text-white shadow-md">
    <div class="max-w-7xl mx-auto px-4 sm:px-6">
      <div class="flex items-center justify-between h-14">
        <!-- Logo -->
        <a href="/" class="flex items-center gap-2 font-semibold text-white hover:text-brand-100">
          <span class="text-xl">⚡</span>
          <span class="hidden sm:inline">Dataspaces Portal</span>
        </a>

        <!-- Desktop nav -->
        <nav class="hidden sm:flex items-center gap-1">
          {#each navItems as item}
            <a
              href={item.href}
              class="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors
                     {$page.url.pathname === item.href || ($page.url.pathname.startsWith(item.href) && item.href !== '/')
                       ? 'bg-brand-900 text-white'
                       : 'text-brand-100 hover:bg-brand-600 hover:text-white'}"
            >
              {item.label}
            </a>
          {/each}
        </nav>

        <!-- Auth -->
        <div class="flex items-center gap-2">
          {#if persona.isAuthenticated}
            <span class="hidden sm:inline text-sm text-brand-200">{persona.name}</span>
            <form method="POST" action="/auth/signout">
              <button class="text-xs px-2 py-1 rounded bg-brand-800 text-brand-100 hover:bg-brand-900">
                Sign out
              </button>
            </form>
          {:else}
            <form method="POST" action="/auth/signin/keycloak">
              <button class="text-xs px-3 py-1.5 rounded-lg bg-white text-brand-700 font-medium hover:bg-brand-50">
                Sign in
              </button>
            </form>
          {/if}

          <!-- Mobile menu toggle -->
          <button
            class="sm:hidden text-white p-1"
            onclick={() => (mobileOpen = !mobileOpen)}
            aria-label="Toggle menu"
          >
            {mobileOpen ? '✕' : '☰'}
          </button>
        </div>
      </div>
    </div>

    <!-- Mobile nav -->
    {#if mobileOpen}
      <nav class="sm:hidden border-t border-brand-600 px-4 py-2 space-y-1">
        {#each navItems as item}
          <a
            href={item.href}
            class="block px-3 py-2 rounded-lg text-sm text-brand-100 hover:bg-brand-600"
            onclick={() => (mobileOpen = false)}
          >
            {item.label}
          </a>
        {/each}
      </nav>
    {/if}
  </header>

  <!-- Main content -->
  <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6">
    {@render children()}
  </main>

  <!-- Footer -->
  <footer class="border-t border-gray-200 bg-white">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 py-3 text-xs text-gray-400 flex items-center justify-between">
      <span>Dataspaces Platform · DSSC Blueprint BB07</span>
      <a href="/ns/energy" class="hover:text-gray-600">ODRL Vocabulary</a>
    </div>
  </footer>
</div>
