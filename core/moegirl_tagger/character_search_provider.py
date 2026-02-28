"""Online character search providers for GUI character onboarding."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
import re
import time
from dataclasses import dataclass
import html
import json
from urllib.parse import parse_qs, quote_plus, urlparse

import requests


ANILIST_URL = "https://graphql.anilist.co"
JIKAN_SEARCH_URL = "https://api.jikan.moe/v4/characters"
JIKAN_TOP_URL = "https://api.jikan.moe/v4/top/characters"
JIKAN_PICTURES_URL = "https://api.jikan.moe/v4/characters/{mal_id}/pictures"
JIKAN_CHARACTER_URL = "https://api.jikan.moe/v4/characters/{mal_id}"
JIKAN_LIMIT_MAX = 25
BANGUMI_SEARCH_URL = "https://api.bgm.tv/v0/search/characters"
BANGUMI_SUBJECT_SEARCH_URL = "https://api.bgm.tv/v0/search/subjects"
BANGUMI_CHARACTER_URL = "https://api.bgm.tv/v0/characters/{character_id}"
BANGUMI_CHARACTER_SUBJECTS_URL = "https://api.bgm.tv/v0/characters/{character_id}/subjects"
BANGUMI_SUBJECT_CHARACTERS_URL = "https://api.bgm.tv/v0/subjects/{subject_id}/characters"
BANGUMI_LIMIT_MAX = 300
DANBOORU_TAGS_URL = "https://danbooru.donmai.us/tags.json"
DANBOORU_POSTS_URL = "https://danbooru.donmai.us/posts.json"
BING_IMAGES_SEARCH_URL = "https://www.bing.com/images/search"
DUCKDUCKGO_SEARCH_URL = "https://duckduckgo.com/"
DUCKDUCKGO_LITE_SEARCH_URL = "https://lite.duckduckgo.com/lite/"
DUCKDUCKGO_IMAGES_URL = "https://duckduckgo.com/i.js"
HTTP_USER_AGENT = "MoeGirlTabProject/1.0"
LOGGER = logging.getLogger("moegirl.character_search")


@dataclass
class SearchCandidate:
    """Normalized character search candidate."""

    provider: str
    provider_entity_id: str
    display_name: str
    source_title: str
    avatar_url: str
    aliases: list[str]


class CharacterSearchProvider:
    """Search characters from AniList with Bangumi/Jikan fallback."""

    def __init__(self, http_client=None) -> None:
        self.http_client = http_client if http_client is not None else requests.Session()
        self._bangumi_subject_title_cache: dict[str, str] = {}

    def search(self, keyword: str, limit: int = 20) -> list[SearchCandidate]:
        query = str(keyword).strip()
        if not query:
            return []

        safe_limit = max(1, min(int(limit), 300))
        query_key = self._match_key(query)
        chinese_query = self._is_chinese_query(query)
        enable_source_title_search = len(query_key) > 2 or (
            self._has_non_ascii_letters(query_key) and len(query_key) >= 2
        )
        overall_start = time.perf_counter()
        LOGGER.info("search start keyword=%s limit=%d", query, safe_limit)

        def fetch_anilist_primary() -> tuple[list[SearchCandidate], list[SearchCandidate], float]:
            begin = time.perf_counter()
            raw_items = self._search_anilist(query, safe_limit)
            return raw_items, self._filter_candidates_by_query(query, raw_items), time.perf_counter() - begin

        def fetch_anilist_source() -> tuple[list[SearchCandidate], float]:
            if not enable_source_title_search:
                return [], 0.0
            begin = time.perf_counter()
            return self._search_anilist_by_source_title(query, safe_limit), time.perf_counter() - begin

        def fetch_bangumi_name() -> tuple[list[SearchCandidate], list[SearchCandidate], float]:
            begin = time.perf_counter()
            raw_items = self._search_bangumi(query, safe_limit)
            return raw_items, self._filter_candidates_by_query(query, raw_items), time.perf_counter() - begin

        def fetch_bangumi_source() -> tuple[list[SearchCandidate], float]:
            if not enable_source_title_search:
                return [], 0.0
            begin = time.perf_counter()
            return self._search_bangumi_by_subject_title(query, safe_limit), time.perf_counter() - begin

        with ThreadPoolExecutor(max_workers=4 if enable_source_title_search else 2) as executor:
            primary_future = executor.submit(fetch_anilist_primary)
            source_future = executor.submit(fetch_anilist_source)
            bangumi_name_future = executor.submit(fetch_bangumi_name)
            bangumi_source_future = executor.submit(fetch_bangumi_source)

            raw_primary, primary, primary_elapsed = primary_future.result()
            source_candidates, source_elapsed = source_future.result()
            raw_bangumi, bangumi_name_candidates, bangumi_elapsed = bangumi_name_future.result()
            bangumi_source_candidates, bangumi_source_elapsed = bangumi_source_future.result()

        LOGGER.info(
            "anilist finished keyword=%s raw_results=%d filtered_results=%d elapsed=%.3fs",
            query,
            len(raw_primary),
            len(primary),
            primary_elapsed,
        )
        source_query_match = False
        if source_candidates:
            LOGGER.info(
                "anilist source-title finished keyword=%s results=%d elapsed=%.3fs",
                query,
                len(source_candidates),
                source_elapsed,
            )
            source_query_match = self._query_matches_any_candidate_source_title(query, source_candidates)

        primary_name_match = self._query_matches_any_candidate_name(query, primary)
        source_preferred = (
            bool(source_candidates)
            and (source_query_match or not primary_name_match)
        )
        anilist_candidates = source_candidates if source_preferred else primary
        anilist_matches_query = (
            self._query_matches_any_candidate_name(query, anilist_candidates)
            or self._query_matches_any_candidate_source_title(query, anilist_candidates)
        )

        bangumi: list[SearchCandidate] = []
        bangumi_name_match = False
        should_query_bangumi = True
        if should_query_bangumi:
            bangumi_name_match = self._query_matches_any_candidate_display_name(query, bangumi_name_candidates)
            LOGGER.info(
                "bangumi character-search finished keyword=%s raw_results=%d filtered_results=%d elapsed=%.3fs",
                query,
                len(raw_bangumi),
                len(bangumi_name_candidates),
                bangumi_elapsed,
            )

            if bangumi_source_candidates:
                LOGGER.info(
                    "bangumi subject-search finished keyword=%s results=%d elapsed=%.3fs",
                    query,
                    len(bangumi_source_candidates),
                    bangumi_source_elapsed,
                )

            if bangumi_source_candidates:
                if bangumi_name_match:
                    bangumi = self._merge_candidates_with_priority(
                        primary=bangumi_name_candidates,
                        supplement=bangumi_source_candidates,
                        limit=safe_limit,
                    )
                else:
                    bangumi = self._merge_candidates_with_priority(
                        primary=bangumi_source_candidates,
                        supplement=bangumi_name_candidates,
                        limit=safe_limit,
                    )
            else:
                bangumi = list(bangumi_name_candidates)

        character_candidates: list[SearchCandidate] = []
        provider_label = "none"
        prefer_bangumi = (
            bool(bangumi)
            and (
                # Simplified/Traditional Chinese query: keep Bangumi at the top.
                chinese_query
                # Character-name query where Bangumi has direct name hit but AniList does not.
                or (bangumi_name_match and not primary_name_match)
                # Work-title query: prefer Bangumi subject-chain characters in the visible top results.
                or (enable_source_title_search and source_preferred and not primary_name_match and not bangumi_name_match)
            )
        )
        if bangumi:
            if anilist_candidates and (anilist_matches_query or source_preferred) and not prefer_bangumi:
                character_candidates = self._merge_candidates_with_priority(
                    primary=anilist_candidates,
                    supplement=bangumi,
                    limit=safe_limit,
                )
                provider_label = "anilist+bangumi"
            else:
                character_candidates = self._merge_candidates_with_priority(
                    primary=bangumi,
                    supplement=anilist_candidates,
                    limit=safe_limit,
                )
                provider_label = "bangumi+anilist" if anilist_candidates else "bangumi"
        elif anilist_candidates and (anilist_matches_query or source_preferred):
            character_candidates = list(anilist_candidates[:safe_limit])
            provider_label = "anilist-source" if source_preferred else "anilist"
        else:
            LOGGER.info("anilist/bangumi empty keyword=%s fallback_to=jikan", query)
            fallback_start = time.perf_counter()
            raw_fallback = self._search_jikan(query, safe_limit)
            fallback = self._filter_candidates_by_query(query, raw_fallback)
            fallback_elapsed = time.perf_counter() - fallback_start
            LOGGER.info(
                "jikan finished keyword=%s raw_results=%d filtered_results=%d elapsed=%.3fs",
                query,
                len(raw_fallback),
                len(fallback),
                fallback_elapsed,
            )
            character_candidates = list(fallback[:safe_limit])
            provider_label = "jikan" if fallback else "none"

        LOGGER.info(
            "search done keyword=%s provider=%s total_results=%d elapsed=%.3fs",
            query,
            provider_label,
            len(character_candidates),
            time.perf_counter() - overall_start,
        )
        self._enrich_bangumi_source_titles(character_candidates, max_enrich=min(20, safe_limit))
        return character_candidates[:safe_limit]

    def _enrich_bangumi_source_titles(self, candidates: list[SearchCandidate], *, max_enrich: int) -> None:
        remaining = max(0, int(max_enrich))
        if remaining <= 0:
            return
        for candidate in candidates:
            if remaining <= 0:
                break
            if str(candidate.provider).strip().lower() != "bangumi":
                continue
            if not self._needs_bangumi_source_enrichment(candidate.source_title):
                continue
            replacement = self._fetch_bangumi_primary_subject_title(candidate.provider_entity_id)
            remaining -= 1
            if replacement:
                candidate.source_title = replacement

    @classmethod
    def _needs_bangumi_source_enrichment(cls, source_title: str) -> bool:
        source = str(source_title or "").strip()
        if not source:
            return True
        return cls._looks_like_url_or_domain(source)

    @staticmethod
    def _looks_like_url_or_domain(value: str) -> bool:
        text = str(value or "").strip().lower()
        if not text:
            return False
        if text.startswith(("http://", "https://", "//")):
            return True
        host = text.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
        if ":" in host:
            host = host.split(":", 1)[0]
        return bool(re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", host))

    def _merge_candidates_with_priority(
        self,
        primary: list[SearchCandidate],
        supplement: list[SearchCandidate],
        limit: int,
    ) -> list[SearchCandidate]:
        safe_limit = max(1, min(int(limit), 300))
        merged: list[SearchCandidate] = []
        seen_provider_entity: set[str] = set()
        seen_name_source: set[str] = set()

        def append_candidate(candidate: SearchCandidate) -> None:
            provider_key = f"{str(candidate.provider).strip().lower()}:{str(candidate.provider_entity_id).strip().lower()}"
            if provider_key.strip(":") and provider_key in seen_provider_entity:
                return
            name_key = self._match_key(candidate.display_name)
            source_key = self._match_key(candidate.source_title)
            name_source_key = f"{name_key}:{source_key}" if source_key else name_key
            if name_source_key and name_source_key in seen_name_source:
                return

            if provider_key.strip(":"):
                seen_provider_entity.add(provider_key)
            if name_source_key:
                seen_name_source.add(name_source_key)
            merged.append(candidate)

        for candidate in list(primary) + list(supplement):
            append_candidate(candidate)
            if len(merged) >= safe_limit:
                break
        return merged

    def fetch_popular_characters(self, limit: int = 100, per_page: int = 50) -> list[SearchCandidate]:
        safe_limit = max(1, min(int(limit), 5000))
        safe_per_page = max(1, min(int(per_page), 50))
        overall_start = time.perf_counter()
        LOGGER.info("popular build start limit=%d per_page=%d", safe_limit, safe_per_page)

        popular: list[SearchCandidate] = []
        seen: set[str] = set()
        page = 1
        while len(popular) < safe_limit:
            page_start = time.perf_counter()
            items = self._fetch_anilist_popular_page(page=page, per_page=safe_per_page)
            LOGGER.info(
                "anilist popular page=%d results=%d elapsed=%.3fs",
                page,
                len(items),
                time.perf_counter() - page_start,
            )
            if not items:
                break
            for candidate in items:
                dedupe_key = f"{candidate.provider}:{candidate.provider_entity_id}".lower()
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                popular.append(candidate)
                if len(popular) >= safe_limit:
                    break
            if len(items) < safe_per_page:
                break
            page += 1

        if popular:
            LOGGER.info(
                "popular build done provider=anilist results=%d elapsed=%.3fs",
                len(popular),
                time.perf_counter() - overall_start,
            )
            return popular[:safe_limit]

        LOGGER.info("popular anilist empty fallback_to=jikan")
        fallback: list[SearchCandidate] = []
        page = 1
        while len(fallback) < safe_limit:
            page_start = time.perf_counter()
            items = self._fetch_jikan_top_page(page=page, per_page=safe_per_page)
            LOGGER.info(
                "jikan top page=%d results=%d elapsed=%.3fs",
                page,
                len(items),
                time.perf_counter() - page_start,
            )
            if not items:
                break
            for candidate in items:
                dedupe_key = f"{candidate.provider}:{candidate.provider_entity_id}".lower()
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                fallback.append(candidate)
                if len(fallback) >= safe_limit:
                    break
            if len(items) < safe_per_page:
                break
            page += 1

        LOGGER.info(
            "popular build done provider=%s results=%d elapsed=%.3fs",
            "jikan" if fallback else "none",
            len(fallback),
            time.perf_counter() - overall_start,
        )
        return fallback[:safe_limit]

    def search_all_sources(self, keyword: str, limit_each: int = 20) -> list[SearchCandidate]:
        query = str(keyword).strip()
        if not query:
            return []

        safe_limit = max(1, min(int(limit_each), 50))
        merged: list[SearchCandidate] = []
        seen: set[str] = set()
        bangumi = self._filter_candidates_by_query(query, self._search_bangumi(query, safe_limit))
        for item in (
            self._search_anilist(query, safe_limit)
            + bangumi
            + self._search_jikan(query, safe_limit)
        ):
            key = f"{item.provider}:{item.provider_entity_id}:{item.display_name}:{item.source_title}".lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    def _query_matches_any_candidate_name(self, query: str, candidates: list[SearchCandidate]) -> bool:
        query_key = self._match_key(query)
        if not query_key:
            return False
        for candidate in candidates:
            for raw_name in [candidate.display_name] + list(candidate.aliases):
                candidate_key = self._match_key(raw_name)
                if not candidate_key:
                    continue
                if self._has_meaningful_substring_match(query_key, candidate_key):
                    return True
        return False

    def _query_matches_any_candidate_display_name(self, query: str, candidates: list[SearchCandidate]) -> bool:
        query_key = self._match_key(query)
        if not query_key:
            return False
        for candidate in candidates:
            candidate_key = self._match_key(candidate.display_name)
            if not candidate_key:
                continue
            if self._has_meaningful_substring_match(query_key, candidate_key):
                return True
        return False

    def _query_matches_any_candidate_source_title(self, query: str, candidates: list[SearchCandidate]) -> bool:
        query_key = self._match_key(query)
        if not query_key:
            return False
        for candidate in candidates:
            source_key = self._match_key(candidate.source_title)
            if not source_key:
                continue
            if self._has_meaningful_substring_match(query_key, source_key):
                return True
        return False

    def _filter_candidates_by_query(self, query: str, candidates: list[SearchCandidate]) -> list[SearchCandidate]:
        return [candidate for candidate in candidates if self._candidate_matches_query(query, candidate)]

    def _candidate_matches_query(self, query: str, candidate: SearchCandidate) -> bool:
        query_key = self._match_key(query)
        if not query_key:
            return False

        raw_query = str(query or "").strip().lower()
        if len(query_key) == 1:
            if not raw_query:
                return False
            raw_fields = [candidate.display_name, candidate.source_title] + list(candidate.aliases)
            return any(raw_query in str(field or "").lower() for field in raw_fields)

        candidate_keys: list[str] = [
            self._match_key(candidate.display_name),
            self._match_key(candidate.source_title),
        ]
        candidate_keys.extend(self._match_key(alias) for alias in candidate.aliases)
        deduped_keys = [key for key in dict.fromkeys(candidate_keys) if key]

        for key in deduped_keys:
            if self._has_meaningful_substring_match(query_key, key):
                return True

        # For CJK-like queries, allow 2+ character overlap as a loose transliteration match.
        if self._has_non_ascii_letters(query_key) and len(query_key) >= 3:
            for key in deduped_keys:
                if not self._has_non_ascii_letters(key):
                    continue
                common_len = self._longest_common_substring_length(query_key, key)
                if common_len >= 2 and (common_len / max(1, len(query_key))) >= 0.67:
                    return True
        return False

    def _is_single_char_query(self, query: str) -> bool:
        return len(self._match_key(query)) == 1

    @staticmethod
    def _has_meaningful_substring_match(query_key: str, candidate_key: str) -> bool:
        query_norm = str(query_key or "").strip()
        candidate_norm = str(candidate_key or "").strip()
        if not query_norm or not candidate_norm:
            return False
        if query_norm in candidate_norm:
            return len(query_norm) >= 2
        if candidate_norm in query_norm:
            return len(candidate_norm) >= 2
        return False

    @staticmethod
    def _longest_common_substring_length(first: str, second: str) -> int:
        left = str(first or "")
        right = str(second or "")
        if not left or not right:
            return 0
        best = 0
        left_len = len(left)
        right_len = len(right)
        for i in range(left_len):
            for j in range(right_len):
                current = 0
                while (
                    i + current < left_len
                    and j + current < right_len
                    and left[i + current] == right[j + current]
                ):
                    current += 1
                if current > best:
                    best = current
        return best

    def collect_reference_image_urls_for_bulk(
        self,
        display_name: str,
        source_title: str = "",
        limit: int = 5,
    ) -> list[str]:
        safe_limit = max(1, min(int(limit), 30))
        name = str(display_name).strip()
        source = str(source_title).strip()
        if not name:
            return []

        urls: list[str] = []
        seen: set[str] = set()

        def append_url(candidate_url: str) -> None:
            url = str(candidate_url).strip()
            if not url or url in seen or len(urls) >= safe_limit:
                return
            seen.add(url)
            urls.append(url)

        for image_url in self._fetch_bing_reference_urls(
            display_name=name,
            source_title=source,
            limit=safe_limit,
        ):
            append_url(image_url)
            if len(urls) >= safe_limit:
                break
        if len(urls) >= safe_limit:
            return urls[:safe_limit]

        for image_url in self._fetch_duckduckgo_reference_urls(
            display_name=name,
            source_title=source,
            limit=safe_limit - len(urls),
        ):
            append_url(image_url)
            if len(urls) >= safe_limit:
                break
        if len(urls) < safe_limit and source:
            for image_url in self._fetch_danbooru_reference_urls(
                display_name=name,
                source_title=source,
                limit=safe_limit - len(urls),
            ):
                append_url(image_url)
                if len(urls) >= safe_limit:
                    break
        return urls[:safe_limit]

    def collect_reference_image_urls(
        self,
        display_name: str,
        source_title: str = "",
        limit: int = 5,
        provider: str = "",
        provider_entity_id: str = "",
    ) -> list[str]:
        safe_limit = max(1, min(int(limit), 30))
        name = str(display_name).strip()
        source = str(source_title).strip()
        primary_urls = self._collect_reference_urls_by_provider_entity(
            provider=provider,
            provider_entity_id=provider_entity_id,
            source_title=source,
            limit=safe_limit,
        )
        urls: list[str] = []
        seen: set[str] = set()

        def append_url(candidate_url: str) -> None:
            url = str(candidate_url).strip()
            if not url or url in seen or len(urls) >= safe_limit:
                return
            seen.add(url)
            urls.append(url)

        for url in primary_urls:
            append_url(url)
        if len(urls) >= safe_limit:
            return urls[:safe_limit]

        if not name:
            return urls[:safe_limit]
        anilist_query = f"{name} {source}".strip()
        anilist_candidates = self._search_anilist(anilist_query, max(10, safe_limit * 3))
        # Jikan search is unstable for "name + source" query strings; use name only, then strict source validation.
        jikan_candidates = self._search_jikan(name, max(10, safe_limit * 3))
        name_key = self._match_key(name)
        source_key = self._match_key(source)

        def candidate_name_matches(candidate: SearchCandidate) -> bool:
            candidate_name_key = self._match_key(candidate.display_name)
            if not name_key:
                return True
            if not candidate_name_key:
                return False
            return name_key in candidate_name_key or candidate_name_key in name_key

        def source_matches_strict(candidate: SearchCandidate) -> bool:
            if not source_key:
                return True
            if candidate.provider != "anilist":
                return False
            candidate_source_key = self._match_key(candidate.source_title)
            if not candidate_source_key:
                return False
            return source_key in candidate_source_key or candidate_source_key in source_key

        filtered_anilist: list[SearchCandidate] = []
        for candidate in anilist_candidates:
            if not candidate_name_matches(candidate):
                continue
            if not source_matches_strict(candidate):
                continue
            filtered_anilist.append(candidate)

        if source_key:
            has_exact_context = bool(str(provider).strip() and str(provider_entity_id).strip())
            for candidate in filtered_anilist:
                append_url(candidate.avatar_url)
                if len(urls) >= safe_limit:
                    break
            matched_source_jikan_ids: set[str] = set()
            if len(urls) < safe_limit:
                for candidate in jikan_candidates:
                    if not candidate_name_matches(candidate):
                        continue
                    if not self._jikan_character_matches_source(candidate.provider_entity_id, source):
                        continue
                    matched_source_jikan_ids.add(str(candidate.provider_entity_id))
                    append_url(candidate.avatar_url)
                    if len(urls) >= safe_limit:
                        break
                    for image_url in self._fetch_jikan_character_pictures(
                        candidate.provider_entity_id,
                        limit=safe_limit - len(urls),
                    ):
                        append_url(image_url)
                        if len(urls) >= safe_limit:
                            break
            if len(urls) < safe_limit and has_exact_context and not matched_source_jikan_ids:
                exact_name_candidates: list[SearchCandidate] = []
                seen_ids: set[str] = set()
                for candidate in jikan_candidates:
                    if self._match_key(candidate.display_name) != name_key:
                        continue
                    candidate_id = str(candidate.provider_entity_id).strip()
                    if not candidate_id or candidate_id in seen_ids:
                        continue
                    seen_ids.add(candidate_id)
                    exact_name_candidates.append(candidate)
                if len(exact_name_candidates) == 1:
                    fallback_candidate = exact_name_candidates[0]
                    append_url(fallback_candidate.avatar_url)
                    if len(urls) < safe_limit:
                        for image_url in self._fetch_jikan_character_pictures(
                            fallback_candidate.provider_entity_id,
                            limit=safe_limit - len(urls),
                        ):
                            append_url(image_url)
                            if len(urls) >= safe_limit:
                                break
            if len(urls) < safe_limit and source:
                for image_url in self._fetch_danbooru_reference_urls(
                    display_name=name,
                    source_title=source,
                    limit=safe_limit - len(urls),
                ):
                    append_url(image_url)
                    if len(urls) >= safe_limit:
                        break
            return urls[:safe_limit]

        merged_candidates: list[SearchCandidate] = []
        merged_seen: set[str] = set()
        for candidate in anilist_candidates + jikan_candidates:
            if not candidate_name_matches(candidate):
                continue
            key = f"{candidate.provider}:{candidate.provider_entity_id}:{candidate.display_name}:{candidate.source_title}".lower()
            if key in merged_seen:
                continue
            merged_seen.add(key)
            merged_candidates.append(candidate)

        for candidate in merged_candidates:
            append_url(candidate.avatar_url)
            if len(urls) >= safe_limit:
                break
            if candidate.provider == "jikan":
                extra_urls = self._fetch_jikan_character_pictures(candidate.provider_entity_id, limit=safe_limit - len(urls))
                for image_url in extra_urls:
                    append_url(image_url)
                    if len(urls) >= safe_limit:
                        break
        return urls[:safe_limit]

    def _collect_reference_urls_by_provider_entity(
        self,
        provider: str,
        provider_entity_id: str,
        source_title: str,
        limit: int,
    ) -> list[str]:
        safe_limit = max(1, min(int(limit), 30))
        normalized_provider = str(provider).strip().lower()
        normalized_id = str(provider_entity_id).strip()
        if not normalized_provider or not normalized_id:
            return []

        if normalized_provider == "anilist":
            return self._fetch_anilist_character_images(
                character_id=normalized_id,
                source_title=source_title,
                limit=safe_limit,
            )
        if normalized_provider == "jikan":
            urls = self._fetch_jikan_character_pictures(character_id=normalized_id, limit=safe_limit)
            if urls:
                return urls[:safe_limit]
            fallback_url = self._fetch_jikan_character_image(character_id=normalized_id)
            if fallback_url:
                return [fallback_url]
        if normalized_provider == "bangumi":
            return self._fetch_bangumi_character_images(character_id=normalized_id, limit=safe_limit)
        return []

    def _build_source_match_keys(self, source_title: str) -> list[str]:
        text = str(source_title).strip()
        if not text:
            return []
        variants = [text]
        for separator in (" - ", " – ", " — ", "|", ":"):
            if separator in text:
                variants.append(text.split(separator, 1)[0])
        if "(" in text:
            variants.append(text.split("(", 1)[0])
        keys: list[str] = []
        seen: set[str] = set()
        for value in variants:
            key = self._match_key(value)
            if not key or key in seen:
                continue
            seen.add(key)
            keys.append(key)
        return keys

    def _build_browser_query(self, display_name: str, source_title: str) -> str:
        name = str(display_name).strip()
        source = str(source_title).strip()
        if not name:
            return ""
        query_terms = [name]
        if source:
            query_terms.append(source)
        query_terms.append("anime character")
        return " ".join(term for term in query_terms if str(term).strip())

    def _build_name_match_keys(self, display_name: str) -> list[str]:
        text = str(display_name).strip()
        if not text:
            return []
        variants = [text]
        parts = [segment for segment in re.split(r"[\s_]+", text) if segment]
        if len(parts) >= 2:
            variants.append(" ".join(parts))
            variants.append(" ".join(reversed(parts)))
        keys: list[str] = []
        seen: set[str] = set()
        for value in variants:
            key = self._match_key(value)
            if not key or key in seen:
                continue
            seen.add(key)
            keys.append(key)
        return keys

    def _source_matches_text(self, text: str, source_keys: list[str]) -> bool:
        if not source_keys:
            return True
        target = self._match_key(text)
        if not target:
            return False
        for key in source_keys:
            if key in target or target in key:
                return True
        return False

    def _name_matches_text(self, text: str, name_keys: list[str]) -> bool:
        if not name_keys:
            return True
        target = self._match_key(text)
        if not target:
            return False
        for key in name_keys:
            if key in target or target in key:
                return True
        return False

    def _fetch_bing_reference_urls(self, display_name: str, source_title: str, limit: int) -> list[str]:
        safe_limit = max(1, min(int(limit), 30))
        query = self._build_browser_query(display_name, source_title)
        if not query:
            return []
        source_keys = self._build_source_match_keys(source_title)
        name_keys = self._build_name_match_keys(display_name)
        urls: list[str] = []
        seen: set[str] = set()

        def collect(strict_source: bool) -> None:
            for first in (1, 36, 71):
                if len(urls) >= safe_limit:
                    return
                try:
                    response = self.http_client.get(
                        BING_IMAGES_SEARCH_URL,
                        params={
                            "q": query,
                            "form": "HDRSC2",
                            "first": first,
                            "tsc": "ImageBasicHover",
                            "safeSearch": "Strict",
                        },
                        headers={"User-Agent": HTTP_USER_AGENT},
                        timeout=16,
                    )
                    response.raise_for_status()
                    body = str(getattr(response, "text", ""))
                except Exception as error:
                    LOGGER.info("bing image fetch failed query=%s first=%d error=%s", query, first, error)
                    return

                matches = list(re.finditer(r'class="iusc"[^>]*\sm="([^"]+)"', body))
                if not matches:
                    continue
                for match in matches:
                    raw_json = html.unescape(str(match.group(1)))
                    try:
                        meta = json.loads(raw_json)
                    except Exception:
                        continue
                    if not isinstance(meta, dict):
                        continue
                    raw_url = meta.get("murl", "")
                    image_url = str(raw_url or "").replace("&amp;", "&").strip()
                    if not image_url or image_url in seen:
                        continue
                    if not image_url.lower().startswith(("http://", "https://")):
                        continue
                    metadata = " ".join(
                        str(meta.get(key, "")).strip()
                        for key in ("t", "desc", "purl", "murl")
                    )
                    if not self._name_matches_text(metadata, name_keys):
                        continue
                    if strict_source and source_keys:
                        if not self._source_matches_text(metadata, source_keys):
                            continue
                    seen.add(image_url)
                    urls.append(image_url)
                    if len(urls) >= safe_limit:
                        return
                if len(urls) >= safe_limit:
                    return

        if source_keys:
            collect(strict_source=True)
        if not urls:
            collect(strict_source=False)
        return urls[:safe_limit]

    def _extract_duckduckgo_vqd(self, query: str) -> str:
        try:
            response = self.http_client.get(
                DUCKDUCKGO_SEARCH_URL,
                params={"q": query, "iax": "images", "ia": "images"},
                headers={"User-Agent": HTTP_USER_AGENT},
                timeout=16,
            )
            response.raise_for_status()
            body = str(getattr(response, "text", ""))
        except Exception as error:
            LOGGER.info("duckduckgo vqd failed query=%s error=%s", query, error)
            return ""
        match = re.search(r"vqd=['\"]([^'\"]+)['\"]", body)
        if match:
            return str(match.group(1)).strip()
        return ""

    @staticmethod
    def _duckduckgo_next_offset(next_path: str, fallback: int) -> int:
        raw = str(next_path or "").strip()
        if not raw:
            return max(0, int(fallback))
        parsed = urlparse(raw)
        values = parse_qs(parsed.query).get("s", [])
        if not values:
            return max(0, int(fallback))
        try:
            offset = int(str(values[0]).strip())
        except (TypeError, ValueError):
            return max(0, int(fallback))
        return max(offset, int(fallback))

    def _fetch_duckduckgo_reference_urls(self, display_name: str, source_title: str, limit: int) -> list[str]:
        safe_limit = max(1, min(int(limit), 30))
        source = str(source_title).strip()
        query = self._build_browser_query(display_name, source_title)
        if not query:
            return []
        vqd = self._extract_duckduckgo_vqd(query)
        if not vqd:
            return []

        referer = f"{DUCKDUCKGO_SEARCH_URL}?q={quote_plus(query)}&iax=images&ia=images"
        source_keys = self._build_source_match_keys(source)
        urls: list[str] = []
        seen: set[str] = set()

        def collect(strict_source: bool) -> None:
            offset = 0
            for _ in range(3):
                if len(urls) >= safe_limit:
                    return
                try:
                    response = self.http_client.get(
                        DUCKDUCKGO_IMAGES_URL,
                        params={
                            "q": query,
                            "vqd": vqd,
                            "o": "json",
                            "l": "wt-wt",
                            "f": ",,,,,",
                            "p": "1",
                            "s": offset,
                        },
                        headers={
                            "User-Agent": HTTP_USER_AGENT,
                            "Referer": referer,
                            "X-Requested-With": "XMLHttpRequest",
                        },
                        timeout=16,
                    )
                    response.raise_for_status()
                    payload = response.json()
                except Exception as error:
                    LOGGER.info("duckduckgo image fetch failed query=%s offset=%d error=%s", query, offset, error)
                    return
                if not isinstance(payload, dict):
                    return
                results = payload.get("results", [])
                if not isinstance(results, list) or not results:
                    return

                before = len(urls)
                for item in results:
                    if not isinstance(item, dict):
                        continue
                    image_url = str(item.get("image") or item.get("thumbnail") or "").strip()
                    if not image_url or image_url in seen:
                        continue
                    if not image_url.lower().startswith(("http://", "https://")):
                        continue
                    if strict_source and source_keys:
                        metadata = " ".join(
                            str(item.get(key, "")).strip()
                            for key in ("title", "url", "source")
                        )
                        if not self._source_matches_text(metadata, source_keys):
                            continue
                    seen.add(image_url)
                    urls.append(image_url)
                    if len(urls) >= safe_limit:
                        return

                fallback_next = offset + max(len(results), 1)
                next_offset = self._duckduckgo_next_offset(payload.get("next", ""), fallback=fallback_next)
                if next_offset <= offset:
                    return
                offset = next_offset
                if len(urls) == before and strict_source:
                    return

        if source_keys:
            collect(strict_source=True)
        if not urls:
            collect(strict_source=False)
        return urls[:safe_limit]

    @staticmethod
    def _to_danbooru_tag_token(value: str) -> str:
        lowered = str(value or "").strip().lower()
        lowered = lowered.replace("’", "'").replace("-", "_").replace(" ", "_")
        lowered = re.sub(r"[^0-9a-z_:']", "_", lowered)
        lowered = re.sub(r"_+", "_", lowered).strip("_")
        return lowered

    def _build_danbooru_name_tokens(self, display_name: str) -> list[str]:
        text = str(display_name).strip()
        if not text:
            return []
        tokens: list[str] = []
        seen: set[str] = set()

        def append(value: str) -> None:
            token = self._to_danbooru_tag_token(value)
            if not token or token in seen:
                return
            seen.add(token)
            tokens.append(token)

        append(text)
        parts = [segment for segment in re.split(r"[\s_]+", text) if segment]
        if len(parts) >= 2:
            append("_".join(parts))
            append("_".join(reversed(parts)))
        return tokens

    def _build_danbooru_source_tokens(self, source_title: str) -> list[str]:
        text = str(source_title).strip()
        if not text:
            return []
        tokens: list[str] = []
        seen: set[str] = set()

        def append(value: str) -> None:
            token = self._to_danbooru_tag_token(value)
            if not token or token in seen:
                return
            seen.add(token)
            tokens.append(token)

        append(text)
        for separator in (" - ", " – ", " — ", "|"):
            if separator in text:
                append(text.split(separator, 1)[0])
        if "(" in text:
            append(text.split("(", 1)[0])
        return tokens

    def _fetch_danbooru_reference_urls(self, display_name: str, source_title: str, limit: int) -> list[str]:
        safe_limit = max(1, min(int(limit), 30))
        name_tokens = self._build_danbooru_name_tokens(display_name)
        source_tokens = self._build_danbooru_source_tokens(source_title)
        if not name_tokens or not source_tokens:
            return []

        candidate_tags: list[str] = []
        candidate_seen: set[str] = set()
        for name_token in name_tokens:
            try:
                response = self.http_client.get(
                    DANBOORU_TAGS_URL,
                    params={
                        "search[name_matches]": f"{name_token}*",
                        "search[category]": 4,
                        "search[order]": "count",
                        "limit": 30,
                    },
                    headers={"User-Agent": HTTP_USER_AGENT},
                    timeout=16,
                )
                response.raise_for_status()
                payload = response.json()
            except Exception:
                payload = []
            if not isinstance(payload, list):
                payload = []
            for item in payload:
                if not isinstance(item, dict):
                    continue
                tag_name = str(item.get("name", "")).strip().lower()
                if not tag_name:
                    continue
                if not any(source_token in tag_name for source_token in source_tokens):
                    continue
                if tag_name in candidate_seen:
                    continue
                candidate_seen.add(tag_name)
                candidate_tags.append(tag_name)
            if candidate_tags:
                break

        if not candidate_tags:
            for name_token in name_tokens:
                for source_token in source_tokens:
                    synthesized = f"{name_token}_({source_token})"
                    if synthesized in candidate_seen:
                        continue
                    candidate_seen.add(synthesized)
                    candidate_tags.append(synthesized)

        urls: list[str] = []
        seen_urls: set[str] = set()
        for tag in candidate_tags:
            if len(urls) >= safe_limit:
                break
            tag_queries = [f"{tag} rating:safe", f"{tag} -rating:e"]
            for query in tag_queries:
                try:
                    response = self.http_client.get(
                        DANBOORU_POSTS_URL,
                        params={"tags": query, "limit": max(10, safe_limit * 4)},
                        headers={"User-Agent": HTTP_USER_AGENT},
                        timeout=16,
                    )
                    response.raise_for_status()
                    payload = response.json()
                except Exception:
                    payload = []
                if not isinstance(payload, list):
                    payload = []
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    raw_url = item.get("file_url") or item.get("large_file_url")
                    url = str(raw_url or "").strip()
                    if not url or url in seen_urls:
                        continue
                    if not url.lower().startswith(("http://", "https://")):
                        continue
                    seen_urls.add(url)
                    urls.append(url)
                    if len(urls) >= safe_limit:
                        break
                if urls:
                    break
        return urls[:safe_limit]

    def _search_anilist(self, keyword: str, limit: int) -> list[SearchCandidate]:
        graphql = """
        query ($search: String, $perPage: Int) {
          Page(page: 1, perPage: $perPage) {
            characters(search: $search, sort: [SEARCH_MATCH, FAVOURITES_DESC]) {
              id
              name {
                full
                native
                userPreferred
                alternative
                alternativeSpoiler
              }
              image {
                large
                medium
              }
              media(perPage: 1, sort: [POPULARITY_DESC]) {
                nodes {
                  title {
                    romaji
                    english
                    native
                  }
                }
              }
            }
          }
        }
        """
        try:
            response = self.http_client.post(
                ANILIST_URL,
                json={"query": graphql, "variables": {"search": keyword, "perPage": limit}},
                timeout=12,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as error:
            LOGGER.warning("anilist request failed keyword=%s error=%s", keyword, error)
            return []
        return self._parse_anilist_characters(payload)

    def _search_anilist_by_source_title(self, keyword: str, limit: int) -> list[SearchCandidate]:
        safe_limit = max(1, min(int(limit), 300))
        media_per_page = max(3, min(12, (safe_limit + 49) // 50))
        character_per_page = max(1, min(100, safe_limit))
        graphql = """
        query ($search: String, $mediaPerPage: Int, $characterPerPage: Int) {
          Page(page: 1, perPage: $mediaPerPage) {
            media(search: $search, sort: [SEARCH_MATCH, POPULARITY_DESC]) {
              title {
                romaji
                english
                native
              }
              characters(perPage: $characterPerPage, sort: [ROLE, RELEVANCE, FAVOURITES_DESC]) {
                edges {
                  node {
                    id
                    name {
                      full
                      native
                      userPreferred
                      alternative
                      alternativeSpoiler
                    }
                    image {
                      large
                      medium
                    }
                  }
                }
              }
            }
          }
        }
        """
        try:
            response = self.http_client.post(
                ANILIST_URL,
                json={
                    "query": graphql,
                    "variables": {
                        "search": keyword,
                        "mediaPerPage": media_per_page,
                        "characterPerPage": character_per_page,
                    },
                },
                timeout=12,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []

        media_items = payload.get("data", {}).get("Page", {}).get("media", []) if isinstance(payload, dict) else []
        if not isinstance(media_items, list):
            return []
        pseudo_characters: list[dict] = []
        for media in media_items:
            if not isinstance(media, dict):
                continue
            title = media.get("title", {})
            edges = media.get("characters", {}).get("edges", []) if isinstance(media.get("characters"), dict) else []
            if not isinstance(edges, list):
                continue
            for edge in edges:
                if not isinstance(edge, dict):
                    continue
                node = edge.get("node", {})
                if not isinstance(node, dict):
                    continue
                pseudo_characters.append(
                    {
                        "id": node.get("id"),
                        "name": node.get("name"),
                        "image": node.get("image"),
                        "media": {"nodes": [{"title": title}]},
                    }
                )
        merged = self._parse_anilist_characters({"data": {"Page": {"characters": pseudo_characters}}})
        return merged[:safe_limit]

    def _fetch_anilist_popular_page(self, page: int, per_page: int) -> list[SearchCandidate]:
        graphql = """
        query ($page: Int, $perPage: Int) {
          Page(page: $page, perPage: $perPage) {
            characters(sort: [FAVOURITES_DESC]) {
              id
              name {
                full
                native
                userPreferred
                alternative
                alternativeSpoiler
              }
              image {
                large
                medium
              }
              media(perPage: 1, sort: [POPULARITY_DESC]) {
                nodes {
                  title {
                    romaji
                    english
                    native
                  }
                }
              }
            }
          }
        }
        """
        try:
            response = self.http_client.post(
                ANILIST_URL,
                json={"query": graphql, "variables": {"page": int(page), "perPage": int(per_page)}},
                timeout=16,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as error:
            LOGGER.warning("anilist popular failed page=%s error=%s", page, error)
            return []
        return self._parse_anilist_characters(payload)

    def _search_jikan(self, keyword: str, limit: int) -> list[SearchCandidate]:
        safe_limit = max(1, min(int(limit), JIKAN_LIMIT_MAX))
        try:
            response = self.http_client.get(
                JIKAN_SEARCH_URL,
                params={"q": keyword, "limit": safe_limit},
                timeout=12,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as error:
            LOGGER.warning("jikan request failed keyword=%s error=%s", keyword, error)
            return []
        return self._parse_jikan_characters(payload)

    def _search_bangumi(self, keyword: str, limit: int) -> list[SearchCandidate]:
        safe_limit = max(1, min(int(limit), BANGUMI_LIMIT_MAX))
        results: list[SearchCandidate] = []
        seen: set[str] = set()
        page_size = 20
        offset = 0

        while len(results) < safe_limit:
            try:
                response = self.http_client.post(
                    BANGUMI_SEARCH_URL,
                    params={"limit": min(page_size, safe_limit - len(results)), "offset": offset},
                    json={"keyword": keyword},
                    headers={"User-Agent": HTTP_USER_AGENT, "Content-Type": "application/json"},
                    timeout=12,
                )
                response.raise_for_status()
                payload = response.json()
            except Exception as error:
                LOGGER.warning("bangumi request failed keyword=%s offset=%s error=%s", keyword, offset, error)
                break

            page_items = self._parse_bangumi_characters(payload)
            if not page_items:
                break

            for candidate in page_items:
                key = f"{str(candidate.provider).strip().lower()}:{str(candidate.provider_entity_id).strip().lower()}"
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                results.append(candidate)
                if len(results) >= safe_limit:
                    break

            raw_items = payload.get("data", []) if isinstance(payload, dict) else []
            if not isinstance(raw_items, list) or len(raw_items) < page_size:
                break
            offset += len(raw_items)

        return results[:safe_limit]

    def _search_bangumi_by_subject_title(self, keyword: str, limit: int) -> list[SearchCandidate]:
        safe_limit = max(1, min(int(limit), BANGUMI_LIMIT_MAX))
        query_key = self._match_key(keyword)
        if not query_key:
            return []

        try:
            response = self.http_client.post(
                BANGUMI_SUBJECT_SEARCH_URL,
                params={"limit": 20, "offset": 0},
                json={"keyword": keyword, "filter": {"type": [1, 2, 4, 6]}},
                headers={"User-Agent": HTTP_USER_AGENT, "Content-Type": "application/json"},
                timeout=12,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as error:
            LOGGER.warning("bangumi subject search failed keyword=%s error=%s", keyword, error)
            return []

        subjects = payload.get("data", []) if isinstance(payload, dict) else []
        if not isinstance(subjects, list):
            return []

        matched_subjects: list[tuple[str, str]] = []
        for item in subjects:
            if not isinstance(item, dict):
                continue
            subject_id = str(item.get("id") or "").strip()
            if not subject_id:
                continue
            subject_title = str(item.get("name_cn") or item.get("name") or "").strip()
            if not subject_title:
                continue
            subject_key = self._match_key(subject_title)
            if not subject_key:
                continue
            if self._has_meaningful_substring_match(query_key, subject_key):
                matched_subjects.append((subject_id, subject_title))

        if not matched_subjects:
            return []

        results: list[SearchCandidate] = []
        seen: set[str] = set()
        max_subjects = min(3, len(matched_subjects))
        for subject_id, subject_title in matched_subjects[:max_subjects]:
            try:
                response = self.http_client.get(
                    BANGUMI_SUBJECT_CHARACTERS_URL.format(subject_id=subject_id),
                    headers={"User-Agent": HTTP_USER_AGENT},
                    timeout=12,
                )
                response.raise_for_status()
                payload = response.json()
            except Exception as error:
                LOGGER.info("bangumi subject characters failed subject_id=%s error=%s", subject_id, error)
                continue

            items: list[object] = []
            if isinstance(payload, list):
                items = payload
            elif isinstance(payload, dict):
                data = payload.get("data", [])
                if isinstance(data, list):
                    items = data

            for raw in items:
                if not isinstance(raw, dict):
                    continue
                entity_id = str(raw.get("id") or "").strip()
                display_name = str(raw.get("name") or "").strip()
                if not entity_id or not display_name:
                    continue
                dedupe_key = f"bangumi:{entity_id}".lower()
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                images = raw.get("images", {}) if isinstance(raw.get("images"), dict) else {}
                avatar_url = str(
                    images.get("large") or images.get("medium") or images.get("small") or images.get("grid") or ""
                ).strip()
                results.append(
                    SearchCandidate(
                        provider="bangumi",
                        provider_entity_id=entity_id,
                        display_name=display_name,
                        source_title=subject_title,
                        avatar_url=avatar_url,
                        aliases=[display_name],
                    )
                )
                if len(results) >= safe_limit:
                    return results[:safe_limit]

        return results[:safe_limit]

    def _fetch_jikan_top_page(self, page: int, per_page: int) -> list[SearchCandidate]:
        safe_per_page = max(1, min(int(per_page), JIKAN_LIMIT_MAX))
        try:
            response = self.http_client.get(
                JIKAN_TOP_URL,
                params={"page": int(page), "limit": safe_per_page},
                timeout=16,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as error:
            LOGGER.warning("jikan top failed page=%s error=%s", page, error)
            return []
        return self._parse_jikan_characters(payload)

    def _fetch_jikan_character_pictures(self, character_id: str, limit: int) -> list[str]:
        safe_limit = max(1, min(int(limit), 30))
        normalized_id = str(character_id).strip()
        if not normalized_id:
            return []
        url = JIKAN_PICTURES_URL.format(mal_id=normalized_id)
        try:
            response = self.http_client.get(url, timeout=16)
            response.raise_for_status()
            payload = response.json()
        except Exception as error:
            LOGGER.info("jikan pictures failed id=%s error=%s", normalized_id, error)
            return []

        items = payload.get("data", [])
        if not isinstance(items, list):
            return []
        result: list[str] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            url = str(item.get("jpg", {}).get("image_url", "")).strip() if isinstance(item.get("jpg"), dict) else ""
            if not url:
                continue
            if url in seen:
                continue
            seen.add(url)
            result.append(url)
            if len(result) >= safe_limit:
                break
        return result

    def _fetch_jikan_character_image(self, character_id: str) -> str:
        normalized_id = str(character_id).strip()
        if not normalized_id:
            return ""
        url = JIKAN_CHARACTER_URL.format(mal_id=normalized_id)
        try:
            response = self.http_client.get(url, timeout=16)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return ""
        data = payload.get("data", {})
        if not isinstance(data, dict):
            return ""
        images = data.get("images", {})
        if not isinstance(images, dict):
            return ""
        jpg = images.get("jpg", {})
        if not isinstance(jpg, dict):
            return ""
        return str(jpg.get("image_url", "")).strip()

    def _fetch_bangumi_character_images(self, character_id: str, limit: int) -> list[str]:
        safe_limit = max(1, min(int(limit), 30))
        normalized_id = str(character_id).strip()
        if not normalized_id:
            return []
        url = BANGUMI_CHARACTER_URL.format(character_id=normalized_id)
        try:
            response = self.http_client.get(
                url,
                headers={"User-Agent": HTTP_USER_AGENT},
                timeout=16,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as error:
            LOGGER.info("bangumi character failed id=%s error=%s", normalized_id, error)
            return []
        images = payload.get("images", {}) if isinstance(payload, dict) else {}
        if not isinstance(images, dict):
            return []

        urls: list[str] = []
        seen: set[str] = set()
        for raw in [images.get("large"), images.get("medium"), images.get("small"), images.get("grid")]:
            image_url = str(raw or "").strip()
            if not image_url or image_url in seen:
                continue
            seen.add(image_url)
            urls.append(image_url)
            if len(urls) >= safe_limit:
                break
        return urls

    def _jikan_character_matches_source(self, character_id: str, source_title: str) -> bool:
        source_key = self._match_key(source_title)
        if not source_key:
            return True
        normalized_id = str(character_id).strip()
        if not normalized_id:
            return False
        url = JIKAN_CHARACTER_URL.format(mal_id=normalized_id)
        try:
            response = self.http_client.get(url, timeout=16)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return False
        data = payload.get("data", {})
        if not isinstance(data, dict):
            return False

        source_names: list[str] = []
        for field in ("anime", "manga"):
            entries = data.get(field, [])
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                title = str(entry.get("title", "")).strip()
                if title:
                    source_names.append(title)
        for field in ("animeography", "mangaography"):
            entries = data.get(field, [])
            if not isinstance(entries, list):
                continue
            node_key = "anime" if field == "animeography" else "manga"
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                node = entry.get(node_key, {})
                if isinstance(node, dict):
                    title = str(node.get("title", "")).strip()
                    if title:
                        source_names.append(title)
                title_direct = str(entry.get("title", "")).strip()
                if title_direct:
                    source_names.append(title_direct)

        for source_name in source_names:
            candidate_key = self._match_key(source_name)
            if candidate_key and (source_key in candidate_key or candidate_key in source_key):
                return True
        return False

    def _fetch_anilist_character_images(self, character_id: str, source_title: str, limit: int) -> list[str]:
        safe_limit = max(1, min(int(limit), 30))
        normalized_id = str(character_id).strip()
        if not normalized_id:
            return []
        graphql = """
        query ($id: Int) {
          Character(id: $id) {
            id
            image {
              large
              medium
            }
            media(perPage: 1, sort: [POPULARITY_DESC]) {
              nodes {
                title {
                  romaji
                  english
                  native
                }
              }
            }
          }
        }
        """
        try:
            response = self.http_client.post(
                ANILIST_URL,
                json={"query": graphql, "variables": {"id": int(normalized_id)}},
                timeout=16,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []
        character = payload.get("data", {}).get("Character", {})
        if not isinstance(character, dict):
            return []

        source_key = self._match_key(source_title)
        if source_key:
            media_nodes = character.get("media", {}).get("nodes", []) if isinstance(character.get("media"), dict) else []
            first = media_nodes[0] if isinstance(media_nodes, list) and media_nodes and isinstance(media_nodes[0], dict) else {}
            titles = first.get("title", {}) if isinstance(first.get("title"), dict) else {}
            candidate_source = str(titles.get("english") or titles.get("romaji") or titles.get("native") or "").strip()
            candidate_source_key = self._match_key(candidate_source)
            if not candidate_source_key or (
                source_key not in candidate_source_key and candidate_source_key not in source_key
            ):
                return []

        image = character.get("image", {})
        if not isinstance(image, dict):
            return []
        urls: list[str] = []
        seen: set[str] = set()
        for raw in [image.get("large"), image.get("medium")]:
            url = str(raw or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            urls.append(url)
            if len(urls) >= safe_limit:
                break
        return urls

    @staticmethod
    def _match_key(value: str) -> str:
        lowered = str(value or "").strip().lower()
        return "".join(char for char in lowered if char.isalnum())

    @staticmethod
    def _has_non_ascii_letters(value: str) -> bool:
        for char in str(value or ""):
            if char.isalpha() and not char.isascii():
                return True
        return False

    @staticmethod
    def _is_chinese_query(value: str) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        has_han = False
        for char in text:
            codepoint = ord(char)
            if (
                0x4E00 <= codepoint <= 0x9FFF
                or 0x3400 <= codepoint <= 0x4DBF
                or 0x20000 <= codepoint <= 0x2A6DF
                or 0x2A700 <= codepoint <= 0x2B73F
                or 0x2B740 <= codepoint <= 0x2B81F
                or 0x2B820 <= codepoint <= 0x2CEAF
                or 0xF900 <= codepoint <= 0xFAFF
            ):
                has_han = True
                continue
            # If kana exists, treat as Japanese input and do not force Bangumi-first.
            if 0x3040 <= codepoint <= 0x30FF:
                return False
        return has_han

    def _is_probable_name_variant(self, alias: str, base_name_keys: set[str]) -> bool:
        text = str(alias or "").strip()
        if not text:
            return False
        if self._has_non_ascii_letters(text):
            return True
        alias_key = self._match_key(text)
        if not alias_key:
            return False
        for key in base_name_keys:
            if not key:
                continue
            if alias_key in key or key in alias_key:
                return True
        return False

    def _parse_anilist_characters(self, payload: dict) -> list[SearchCandidate]:
        characters = (
            payload.get("data", {})
            .get("Page", {})
            .get("characters", [])
        )
        if not isinstance(characters, list):
            return []

        result: list[SearchCandidate] = []
        seen: set[str] = set()
        for item in characters:
            if not isinstance(item, dict):
                continue
            entity_id = str(item.get("id", "")).strip()
            names = item.get("name", {}) if isinstance(item.get("name"), dict) else {}
            full_name = str(names.get("full") or names.get("userPreferred") or names.get("native") or "").strip()
            if not full_name:
                continue

            media_nodes = item.get("media", {}).get("nodes", []) if isinstance(item.get("media"), dict) else []
            source_title = ""
            if media_nodes and isinstance(media_nodes, list):
                first = media_nodes[0] if isinstance(media_nodes[0], dict) else {}
                titles = first.get("title", {}) if isinstance(first.get("title"), dict) else {}
                source_title = str(titles.get("english") or titles.get("romaji") or titles.get("native") or "").strip()

            image = item.get("image", {}) if isinstance(item.get("image"), dict) else {}
            avatar_url = str(image.get("large") or image.get("medium") or "").strip()

            aliases: list[str] = []
            base_name_keys: set[str] = set()

            def append_alias(raw: object) -> None:
                text = str(raw or "").strip()
                if text and text not in aliases:
                    aliases.append(text)
                    key = self._match_key(text)
                    if key:
                        base_name_keys.add(key)

            for raw in [names.get("full"), names.get("native"), names.get("userPreferred")]:
                append_alias(raw)
            for key in ("alternative", "alternativeSpoiler"):
                extra = names.get(key)
                if isinstance(extra, list):
                    for raw in extra:
                        text = str(raw or "").strip()
                        if self._is_probable_name_variant(text, base_name_keys):
                            append_alias(text)
                elif isinstance(extra, str):
                    if self._is_probable_name_variant(extra, base_name_keys):
                        append_alias(extra)

            unique_key = f"anilist:{entity_id}:{full_name}:{source_title}".lower()
            if unique_key in seen:
                continue
            seen.add(unique_key)

            result.append(
                SearchCandidate(
                    provider="anilist",
                    provider_entity_id=entity_id,
                    display_name=full_name,
                    source_title=source_title,
                    avatar_url=avatar_url,
                    aliases=aliases,
                )
            )
        return result

    @staticmethod
    def _split_alias_text(value: str) -> list[str]:
        text = str(value or "").strip()
        if not text:
            return []
        parts = re.split(r"[／/|,，、]+", text)
        result: list[str] = []
        seen: set[str] = set()
        for raw in parts:
            item = str(raw or "").strip()
            if not item or item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

    @staticmethod
    def _extract_bangumi_source_title_from_infobox(infobox: object) -> str:
        """Extract likely source title from Bangumi infobox fields."""
        if not isinstance(infobox, list):
            return ""
        source_key_candidates = ("引用来源", "出处", "来源", "所属作品", "登场作品")

        def pick_text(raw: object) -> str:
            text = str(raw or "").strip()
            return text

        for entry in infobox:
            if not isinstance(entry, dict):
                continue
            key_text = str(entry.get("key") or "").strip()
            if not key_text or not any(candidate in key_text for candidate in source_key_candidates):
                continue
            value = entry.get("value")
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        text = pick_text(item.get("v") or item.get("k"))
                    else:
                        text = pick_text(item)
                    if text and not CharacterSearchProvider._looks_like_url_or_domain(text):
                        return text
            elif isinstance(value, dict):
                text = pick_text(value.get("v") or value.get("k"))
                if text and not CharacterSearchProvider._looks_like_url_or_domain(text):
                    return text
            else:
                text = pick_text(value)
                if text and not CharacterSearchProvider._looks_like_url_or_domain(text):
                    return text
        return ""

    def _fetch_bangumi_primary_subject_title(self, character_id: str) -> str:
        """Fetch first related subject title from Bangumi for a character."""
        normalized_id = str(character_id).strip()
        if not normalized_id:
            return ""
        if normalized_id in self._bangumi_subject_title_cache:
            return self._bangumi_subject_title_cache[normalized_id]

        url = BANGUMI_CHARACTER_SUBJECTS_URL.format(character_id=normalized_id)
        try:
            response = self.http_client.get(
                url,
                headers={"User-Agent": HTTP_USER_AGENT},
                timeout=12,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as error:
            LOGGER.info("bangumi subjects failed id=%s error=%s", normalized_id, error)
            self._bangumi_subject_title_cache[normalized_id] = ""
            return ""

        if not isinstance(payload, list):
            self._bangumi_subject_title_cache[normalized_id] = ""
            return ""
        for item in payload:
            if not isinstance(item, dict):
                continue
            title = str(item.get("name_cn") or item.get("name") or "").strip()
            if title:
                self._bangumi_subject_title_cache[normalized_id] = title
                return title
        self._bangumi_subject_title_cache[normalized_id] = ""
        return ""

    def _parse_bangumi_characters(self, payload: dict, *, enrich_source_title: bool = False) -> list[SearchCandidate]:
        items = payload.get("data", [])
        if not isinstance(items, list):
            return []

        result: list[SearchCandidate] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            entity_id = str(item.get("id", "")).strip()
            display_name = str(item.get("name") or "").strip()
            if not display_name:
                continue

            images = item.get("images", {}) if isinstance(item.get("images"), dict) else {}
            avatar_url = str(
                images.get("large") or images.get("medium") or images.get("small") or images.get("grid") or ""
            ).strip()
            infobox = item.get("infobox")
            source_title = self._extract_bangumi_source_title_from_infobox(infobox)
            if not source_title and enrich_source_title:
                source_title = self._fetch_bangumi_primary_subject_title(entity_id)

            aliases: list[str] = []
            alias_seen: set[str] = set()

            def append_alias(raw: object) -> None:
                text = str(raw or "").strip()
                if not text:
                    return
                for alias in self._split_alias_text(text):
                    if alias in alias_seen:
                        continue
                    alias_seen.add(alias)
                    aliases.append(alias)

            append_alias(display_name)
            if isinstance(infobox, list):
                for entry in infobox:
                    if not isinstance(entry, dict):
                        continue
                    key_text = str(entry.get("key") or "").strip()
                    if not key_text:
                        continue
                    if ("名" not in key_text) and ("别名" not in key_text) and ("昵称" not in key_text):
                        continue
                    value = entry.get("value")
                    if isinstance(value, list):
                        for nested in value:
                            if isinstance(nested, dict):
                                append_alias(nested.get("v") or nested.get("k"))
                            else:
                                append_alias(nested)
                    elif isinstance(value, dict):
                        append_alias(value.get("v") or value.get("k"))
                    else:
                        append_alias(value)

            unique_key = f"bangumi:{entity_id}:{display_name}".lower()
            if unique_key in seen:
                continue
            seen.add(unique_key)

            result.append(
                SearchCandidate(
                    provider="bangumi",
                    provider_entity_id=entity_id,
                    display_name=display_name,
                    source_title=source_title,
                    avatar_url=avatar_url,
                    aliases=aliases,
                )
            )
        return result

    def _parse_jikan_characters(self, payload: dict) -> list[SearchCandidate]:
        items = payload.get("data", [])
        if not isinstance(items, list):
            return []

        result: list[SearchCandidate] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            entity_id = str(item.get("mal_id", "")).strip()
            display_name = str(item.get("name") or item.get("name_kanji") or "").strip()
            if not display_name:
                continue

            source_title = "MyAnimeList"
            avatar_url = (
                str(
                    item.get("images", {})
                    .get("jpg", {})
                    .get("image_url", "")
                ).strip()
                if isinstance(item.get("images"), dict)
                else ""
            )
            aliases: list[str] = []
            base_name_keys: set[str] = set()

            def append_alias(raw: object) -> None:
                text = str(raw or "").strip()
                if text and text not in aliases:
                    aliases.append(text)
                    key = self._match_key(text)
                    if key:
                        base_name_keys.add(key)

            for raw in [item.get("name"), item.get("name_kanji")]:
                append_alias(raw)
            nicknames = item.get("nicknames")
            if isinstance(nicknames, list):
                for raw in nicknames:
                    text = str(raw or "").strip()
                    if self._is_probable_name_variant(text, base_name_keys):
                        append_alias(text)
            elif isinstance(nicknames, str):
                if self._is_probable_name_variant(nicknames, base_name_keys):
                    append_alias(nicknames)

            unique_key = f"jikan:{entity_id}:{display_name}".lower()
            if unique_key in seen:
                continue
            seen.add(unique_key)

            result.append(
                SearchCandidate(
                    provider="jikan",
                    provider_entity_id=entity_id,
                    display_name=display_name,
                    source_title=source_title,
                    avatar_url=avatar_url,
                    aliases=aliases,
                )
            )
        return result
