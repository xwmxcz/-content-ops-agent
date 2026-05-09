#!/usr/bin/env python3
"""Scaffold a Vue page plus optional API and Pinia store files for this repo."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / 'frontend' / 'src' / 'router' / 'index.ts').exists():
            return candidate
    raise RuntimeError('Could not locate repository root containing frontend/src/router/index.ts')


def split_words(value: str) -> list[str]:
    raw_parts = re.split(r'[^A-Za-z0-9]+', value)
    words: list[str] = []
    for part in raw_parts:
        if not part:
            continue
        words.extend(re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+', part))
    return [w.lower() for w in words if w]


def to_pascal(value: str) -> str:
    words = split_words(value)
    if not words:
        raise ValueError('Name must contain at least one letter or number')
    return ''.join(word.capitalize() for word in words)


def to_kebab(value: str) -> str:
    words = split_words(value)
    if not words:
        raise ValueError('Name must contain at least one letter or number')
    return '-'.join(words)


def ensure_absent(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f'File already exists: {path}. Use --force to overwrite.')


def write_text(path: Path, content: str, force: bool) -> None:
    ensure_absent(path, force)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def render_api_module(pascal_name: str, func_name: str) -> str:
    return f"""import {{ api }} from './index'

export interface {pascal_name}SummaryItem {{
  label: string
  value: string
}}

export async function {func_name}(): Promise<{pascal_name}SummaryItem[]> {{
  const {{ data }} = await api.get<{pascal_name}SummaryItem[]>('/TODO-REPLACE-ME')
  return data
}}
"""


def render_store_module(kebab_name: str, pascal_name: str, module_name: str, func_name: str, with_api: bool) -> str:
    if with_api:
        body = f"""import {{ defineStore }} from 'pinia'
import {{ {func_name}, type {pascal_name}SummaryItem }} from '../api/{module_name}'

export const use{pascal_name}Store = defineStore('{kebab_name}', {{
  state: () => ({{
    items: [] as {pascal_name}SummaryItem[],
    loading: false,
    error: ''
  }}),
  actions: {{
    async refresh() {{
      this.loading = true
      this.error = ''
      try {{
        this.items = await {func_name}()
      }} catch (error) {{
        this.error = error instanceof Error ? error.message : 'Request failed'
      }} finally {{
        this.loading = false
      }}
    }}
  }}
}})
"""
    else:
        body = f"""import {{ defineStore }} from 'pinia'

export const use{pascal_name}Store = defineStore('{kebab_name}', {{
  state: () => ({{
    items: [] as Array<{{ label: string; value: string }}>,
    loading: false,
    error: ''
  }}),
  actions: {{
    async refresh() {{
      this.loading = true
      this.error = ''
      try {{
        // TODO: call an existing API client here
        this.items = [
          {{ label: 'placeholder', value: 'replace me' }}
        ]
      }} catch (error) {{
        this.error = error instanceof Error ? error.message : 'Request failed'
      }} finally {{
        this.loading = false
      }}
    }}
  }}
}})
"""
    return body


def render_view_module(pascal_name: str, module_name: str, func_name: str, with_api: bool, with_store: bool) -> str:
    if with_store:
        script = f"""<script setup lang=\"ts\">
import {{ computed, onMounted }} from 'vue'
import {{ use{pascal_name}Store }} from '../stores/{module_name}'

const pageTitle = '{pascal_name}'
const store = use{pascal_name}Store()

const loading = computed(() => store.loading)
const error = computed(() => store.error)
const items = computed(() => store.items)

async function refresh() {{
  await store.refresh()
}}

onMounted(refresh)
</script>
"""
    elif with_api:
        script = f"""<script setup lang=\"ts\">
import {{ onMounted, ref }} from 'vue'
import {{ {func_name}, type {pascal_name}SummaryItem }} from '../api/{module_name}'

const pageTitle = '{pascal_name}'
const loading = ref(false)
const error = ref('')
const items = ref<{pascal_name}SummaryItem[]>([])

async function refresh() {{
  loading.value = true
  error.value = ''
  try {{
    items.value = await {func_name}()
  }} catch (err) {{
    error.value = err instanceof Error ? err.message : 'Request failed'
  }} finally {{
    loading.value = false
  }}
}}

onMounted(refresh)
</script>
"""
    else:
        script = f"""<script setup lang=\"ts\">
import {{ ref }} from 'vue'

const pageTitle = '{pascal_name}'
const loading = ref(false)
const error = ref('')
const items = ref([
  {{ label: 'placeholder', value: 'replace me' }}
])

async function refresh() {{
  // TODO: wire API call and loading state
}}
</script>
"""

    template = """<template>
  <div class=\"page-shell\">
    <header class=\"page-header\">
      <h1>{{ pageTitle }}</h1>
      <el-button type=\"primary\" :loading=\"loading\" @click=\"refresh\">Refresh</el-button>
    </header>

    <el-alert v-if=\"error\" :title=\"error\" type=\"error\" show-icon :closable=\"false\" class=\"page-alert\" />

    <el-skeleton v-if=\"loading\" :rows=\"6\" animated />

    <el-empty v-else-if=\"!items.length\" description=\"No data\" />

    <el-row v-else :gutter=\"12\">
      <el-col v-for=\"item in items\" :key=\"item.label\" :xs=\"24\" :sm=\"12\" :lg=\"8\">
        <el-card shadow=\"hover\" class=\"metric-card\">
          <div class=\"metric-label\">{{ item.label }}</div>
          <div class=\"metric-value\">{{ item.value }}</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.page-shell {
  display: grid;
  gap: 16px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.page-header h1 {
  margin: 0;
  font-size: 22px;
}

.page-alert {
  margin: 4px 0;
}

.metric-card {
  min-height: 96px;
}

.metric-label {
  color: #64748b;
  font-size: 13px;
}

.metric-value {
  margin-top: 8px;
  font-size: 20px;
  font-weight: 600;
}
</style>
"""
    return script + '\n' + template


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Scaffold frontend page, API module, and store module.')
    parser.add_argument('--name', required=True, help='Page name, for example TrendsBoard')
    parser.add_argument('--route', help='Route path, for example /trends')
    parser.add_argument('--route-name', help='Route name, for example trends')
    parser.add_argument('--with-api', action='store_true', help='Create frontend/src/api/<module>.ts')
    parser.add_argument('--with-store', action='store_true', help='Create frontend/src/stores/<module>.ts')
    parser.add_argument('--force', action='store_true', help='Overwrite existing files')
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    script_path = Path(__file__).resolve()
    repo_root = find_repo_root(script_path)

    pascal_name = to_pascal(args.name)
    kebab_name = to_kebab(args.name)
    module_name = kebab_name.replace('-', '_')

    route_path = args.route or f'/{kebab_name}'
    route_name = args.route_name or kebab_name
    view_filename = f'{pascal_name}.vue'

    view_path = repo_root / 'frontend' / 'src' / 'views' / view_filename
    api_path = repo_root / 'frontend' / 'src' / 'api' / f'{module_name}.ts'
    store_path = repo_root / 'frontend' / 'src' / 'stores' / f'{module_name}.ts'

    api_func_name = f'fetch{pascal_name}Summary'

    write_text(
        view_path,
        render_view_module(pascal_name, module_name, api_func_name, args.with_api, args.with_store),
        args.force,
    )

    if args.with_api:
        write_text(api_path, render_api_module(pascal_name, api_func_name), args.force)

    if args.with_store:
        write_text(
            store_path,
            render_store_module(kebab_name, pascal_name, module_name, api_func_name, args.with_api),
            args.force,
        )

    print('Created files:')
    print(f'- {view_path.relative_to(repo_root)}')
    if args.with_api:
        print(f'- {api_path.relative_to(repo_root)}')
    if args.with_store:
        print(f'- {store_path.relative_to(repo_root)}')

    print('\nAdd this route in frontend/src/router/index.ts:')
    print(
        f"{{ path: '{route_path}', name: '{route_name}', component: () => import('../views/{view_filename}') }}"
    )

    return 0


if __name__ == '__main__':
    raise SystemExit(main())