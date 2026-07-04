# First Run

The first time you run Achew, you will need to complete **Audiobookshelf Setup**. You can also optionally complete **LLM Setup**, or skip it and come back later.

## Audiobookshelf setup

This step is required, as Achew requires access to your Audiobookshelf server to find audiobooks and save chapter data.

1. In your Audiobookshelf instance, [create an API key](https://www.audiobookshelf.org/guides/api-keys/#creating-api-keys){:target="_blank"}.
2. In Achew's **Audiobookshelf Setup** screen, enter:
    - **Your Audiobookshelf Server URL:**  Including scheme and port, e.g. `http://192.168.1.10:13378` or `https://my-abs-server.com`
    - **API key:**  The key you just created.
3. Click **Validate & Save**. Achew contacts the server and confirms the key is valid.

## LLM Setup

This step is optional, but is necessary for [AI Cleanup](../editor/ai-cleanup.md). You can skip this step and come back later.

Achew supports multiple LLM providers:

| Provider | Type | Free tier? |
|---|---|---|
| **OpenAI** | Cloud API | No |
| **Anthropic Claude** | Cloud API | No |
| **Google Gemini** | Cloud API | Yes, limited [free tier](https://ai.google.dev/gemini-api/docs/rate-limits){:target="_blank"} |
| **OpenRouter** | Cloud API | Varies |
| **GitHub Copilot** | Cloud API | Yes, limited [monthly credits](https://docs.github.com/en/copilot/concepts/billing/usage-based-billing-for-individuals){:target="_blank"} |
| **Ollama** | Local server | Free, unlimited |
| **LM Studio** | Local server | Free, unlimited |

At least one provider must be configured in order to use AI Cleanup. For each provider you want to enable, create and paste the API key (or host URL for local servers) and click **Validate**. See [LLM Providers](../getting-started/setup-llm-providers.md) for full setup details, including [free options](../getting-started/setup-llm-providers.md#free-options) if you don't have any paid accounts.

## After setup

Once the initial setup is complete, Achew drops you onto the main screen. Type the first few letters of an audiobook title into the search bar, pick a book, and click **Start**. 

![Book search screen](../img/title-search-light.webp#only-light)
![Book search screen](../img/title-search-dark.webp#only-dark)

The audiobook's files will be downloaded and prepared for processing, after which you may continue by choosing a [workflow](../getting-started/workflows-overview.md).

## Theme

Clicking the sun/moon icon near the top right corner of the page will toggle between light mode and dark mode.

## Returning to setup

From any screen, click the gear icon in top right corner to show the **Settings** dropdown, which includes quick links to Audiobookshelf Setup, LLM Setup, and Transcription Settings:

![Settings dropdown](../img/settings-dropdown-light.webp#only-light){ width="240"; .center }
![Settings dropdown](../img/settings-dropdown-dark.webp#only-dark){ width="240"; .center }

You can change your Transcription settings and LLM settings at any time without losing your current work. It is not recommended to change your Audiobookshelf settings if you're in the middle of processing an audiobook.
