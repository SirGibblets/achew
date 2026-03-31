<script>
    import {onMount, onDestroy} from 'svelte';
    import {chapterSearch} from '../../stores/chapterSearch.js';
    import LandingPage from './LandingPage.svelte';
    import SearchingPage from './SearchingPage.svelte';
    import ResultsPage from './ResultsPage.svelte';
    import StatsPage from './StatsPage.svelte';

    onMount(() => {
        chapterSearch.connect();
    });

    onDestroy(() => {
        chapterSearch.disconnect();
    });
</script>

<div class="chapter-search">
    {#if $chapterSearch.page === 'searching'}
        <SearchingPage />
    {:else if $chapterSearch.page === 'results'}
        <ResultsPage />
    {:else if $chapterSearch.page === 'stats'}
        <StatsPage />
    {:else}
        <LandingPage />
    {/if}
</div>

<style>
    .chapter-search {
        width: 100%;
        display: flex;
        flex-direction: column;
    }
</style>
