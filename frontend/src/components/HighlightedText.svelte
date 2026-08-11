<script lang="ts">
  import { splitHighlight } from '../utils/highlight';

  interface Props {
    text?: string | null;
    /** Substring to mark. Pass an empty string to render plain text. */
    query?: string;
  }

  let { text = '', query = '' }: Props = $props();

  let segments = $derived(splitHighlight(text ?? '', query));
</script>

<!--
  Segments are rendered as nodes rather than an HTML string: both the query and
  the Audiobookshelf metadata are untrusted input.
-->
{#each segments as segment}{#if segment.hit}<mark>{segment.text}</mark>{:else}{segment.text}{/if}{/each}
