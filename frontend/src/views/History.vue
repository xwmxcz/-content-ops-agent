<template>
  <div class="page history-page">
    <section class="history-hero">
      <div>
        <span class="hero-kicker">内容库</span>
        <h1 class="page-title">历史内容</h1>
        <p class="page-subtitle">查看内容、补充素材、发起小红书发布，并管理归档或删除本地记录。</p>
      </div>
      <div class="hero-actions">
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </div>
    </section>

    <section class="section filter-section">
      <div class="filter-grid">
        <el-input v-model="query" placeholder="搜索标题或正文" />
        <el-select v-model="filters.content_type" clearable placeholder="内容类型">
          <el-option v-for="item in CONTENT_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="状态">
          <el-option label="草稿" value="draft" />
          <el-option label="已打磨" value="refined" />
          <el-option label="已定时" value="scheduled" />
          <el-option label="已发布" value="published" />
          <el-option label="已归档" value="archived" />
          <el-option label="Agent 成稿" value="agent_final" />
        </el-select>
        <el-button type="primary" @click="load">筛选</el-button>
      </div>
    </section>

    <section class="results-grid">
      <div class="section list-section">
        <div class="section-head">
          <div>
            <span class="section-kicker">列表</span>
            <h2>内容列表</h2>
          </div>
          <div class="list-actions">
            <span class="section-pill">{{ filteredItems.length }} 条</span>
            <el-button v-if="!selectionMode" @click="enterSelectionMode">批量选择</el-button>
            <el-button v-else @click="exitSelectionMode">退出选择</el-button>
          </div>
        </div>

        <div v-if="selectionMode" class="selection-toolbar">
          <div class="selection-copy">
            <strong>已选择 {{ selectedIds.length }} 条</strong>
            <span>只会处理当前筛选结果中的选中项</span>
          </div>
          <div class="selection-actions">
            <el-button @click="toggleSelectAllVisible">
              {{ allVisibleSelected ? '取消全选' : '全选当前结果' }}
            </el-button>
            <el-button :disabled="!selectedIds.length" @click="clearSelection">清空选择</el-button>
            <el-button
              :icon="FolderDelete"
              :loading="isBulkArchiving"
              :disabled="!selectedIds.length"
              @click="archiveSelectedBatch"
            >
              批量归档
            </el-button>
            <el-button
              type="danger"
              :icon="Delete"
              :loading="isBulkDeleting"
              :disabled="!selectedIds.length"
              @click="deleteSelectedBatch"
            >
              批量删除本地内容
            </el-button>
          </div>
        </div>

        <el-empty v-if="!filteredItems.length && !loading" description="暂无匹配内容" />
        <div v-else class="library-grid">
          <div
            v-for="item in filteredItems"
            :key="item.id"
            class="library-entry"
            :class="{ selected: isSelected(item.id), selectable: selectionMode }"
          >
            <label v-if="selectionMode" class="card-checkbox" @click.stop>
              <el-checkbox :model-value="isSelected(item.id)" @change="onSelectionChange(item.id, $event)" />
            </label>
            <button
              type="button"
              class="library-card"
              :aria-label="selectionMode ? `选择内容 ${item.title || item.id}` : `查看内容 ${item.title || item.id}`"
              @click="handleCardClick(item.id)"
            >
              <ContentCard :item="item" />
            </button>
          </div>
        </div>
      </div>

      <div class="section detail-section">
        <div class="section-head">
          <div>
            <span class="section-kicker">详情</span>
            <h2>{{ selected?.title || '内容详情' }}</h2>
          </div>
          <div class="detail-actions">
            <el-button :icon="Edit" :disabled="!selected || selectionMode" @click="goRefine">去打磨</el-button>
            <el-button :icon="DocumentCopy" :disabled="!selected?.content" @click="copyContent">复制</el-button>
            <el-button :icon="FolderDelete" :disabled="!selected || selectionMode" @click="archiveSelectedSingle">归档</el-button>
            <el-button type="danger" :icon="Delete" :disabled="!selected || selectionMode" @click="deleteSelectedSingle">
              删除本地内容
            </el-button>
          </div>
        </div>

        <el-empty
          v-if="!selected"
          :description="selectionMode ? '批量选择模式下，点击左侧卡片可选中或取消选中。' : '点击左侧内容查看详情'"
        />
        <div v-else class="detail-shell">
          <div class="detail-meta">
            <div class="meta-card">
              <span>类型</span>
              <strong>{{ getContentTypeLabel(selected.content_type) }}</strong>
            </div>
            <div class="meta-card">
              <span>风格</span>
              <strong>{{ getStyleLabel(selected.style) }}</strong>
            </div>
            <div class="meta-card">
              <span>状态</span>
              <strong>{{ getStatusLabel(selected.status) }}</strong>
            </div>
          </div>

          <div class="content-preview">{{ selected.content }}</div>

          <section class="detail-block">
            <div class="block-head">
              <div>
                <span class="section-kicker">素材</span>
                <h3>素材管理</h3>
              </div>
              <div class="upload-actions">
                <label class="upload-trigger">
                  <input class="hidden-input" type="file" accept="image/*" multiple @change="onImageFilesSelected" />
                  <el-icon><UploadFilled /></el-icon>
                  <span>{{ uploadingImages ? '上传中...' : '上传图片' }}</span>
                </label>
                <label class="upload-trigger">
                  <input class="hidden-input" type="file" accept="video/*" @change="onVideoFileSelected" />
                  <el-icon><VideoPlay /></el-icon>
                  <span>{{ uploadingVideo ? '上传中...' : '上传视频' }}</span>
                </label>
              </div>
            </div>

            <el-alert
              v-if="!mediaAssets.length"
              type="info"
              :closable="false"
              title="可以先只保存文字。发布到小红书时，图文至少需要 1 张图片，视频发布需要 1 个视频。"
            />

            <div v-else class="media-grid">
              <article v-for="asset in mediaAssets" :key="asset.id" class="media-card">
                <div class="media-preview">
                  <img v-if="asset.media_type === 'image'" :src="asset.file_url" :alt="asset.file_name" />
                  <video v-else :src="asset.file_url" controls preload="metadata" />
                </div>
                <div class="media-copy">
                  <strong>{{ asset.file_name }}</strong>
                  <span>{{ asset.media_type === 'image' ? '图片' : '视频' }}</span>
                </div>
                <el-button text type="danger" :icon="Delete" @click="removeMedia(asset.id)">删除</el-button>
              </article>
            </div>
          </section>

          <section class="detail-block">
            <div class="block-head">
              <div>
                <span class="section-kicker">发布</span>
                <h3>小红书发布</h3>
              </div>
              <span class="login-badge" :class="{ offline: !loginStatus?.connected }">
                {{ loginStatusLabel }}
              </span>
            </div>

            <div class="publish-panel">
              <div class="publish-grid">
                <div class="field">
                  <span>发布类型</span>
                  <el-radio-group v-model="publishForm.publish_type">
                    <el-radio-button label="image_post">图文</el-radio-button>
                    <el-radio-button label="video_post">视频</el-radio-button>
                  </el-radio-group>
                </div>

                <div class="field">
                  <span>标题覆盖</span>
                  <el-input v-model="publishForm.title" placeholder="可选，不填则使用当前标题" />
                </div>

                <div class="field field-wide">
                  <span>正文覆盖</span>
                  <el-input
                    v-model="publishForm.content"
                    type="textarea"
                    :rows="4"
                    resize="none"
                    placeholder="可选，不填则使用当前内容正文"
                  />
                </div>

                <div class="field">
                  <span>定时发布</span>
                  <el-date-picker
                    v-model="publishForm.scheduled_at"
                    type="datetime"
                    value-format="YYYY-MM-DDTHH:mm:ss"
                    placeholder="选择未来时间"
                  />
                </div>
              </div>

              <el-alert v-if="publishHint" type="warning" :closable="false" :title="publishHint" />

              <div class="publish-actions">
                <el-button
                  type="primary"
                  :icon="Promotion"
                  :disabled="!canPublishNow"
                  :loading="publishingNow"
                  @click="publishNow"
                >
                  立即发布
                </el-button>
                <el-button
                  :icon="Clock"
                  :disabled="!canSchedulePublish"
                  :loading="schedulingPublish"
                  @click="schedulePublish"
                >
                  定时发布
                </el-button>
              </div>
            </div>

            <div class="publication-list">
              <article v-for="publication in publications" :key="publication.id" class="publication-card">
                <div class="publication-topline">
                  <strong>{{ publication.publish_type === 'image_post' ? '图文发布' : '视频发布' }}</strong>
                  <span>{{ getStatusLabel(publication.status) }}</span>
                </div>
                <p>{{ publication.title || selected.title || '未命名发布' }}</p>
                <small v-if="publication.scheduled_at">定时：{{ formatDate(publication.scheduled_at) }}</small>
                <small v-else-if="publication.published_at">完成：{{ formatDate(publication.published_at) }}</small>
                <small v-else>创建：{{ formatDate(publication.created_at) }}</small>
                <small v-if="publication.error_message" class="error-copy">{{ publication.error_message }}</small>
              </article>
              <el-empty v-if="!publications.length" description="暂无发布记录" />
            </div>
          </section>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElAlert } from 'element-plus/es/components/alert/index'
import { ElCheckbox } from 'element-plus/es/components/checkbox/index'
import { ElDatePicker } from 'element-plus/es/components/date-picker/index'
import { ElEmpty } from 'element-plus/es/components/empty/index'
import { ElMessage } from 'element-plus/es/components/message/index'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { ElRadioButton, ElRadioGroup } from 'element-plus/es/components/radio/index'
import 'element-plus/es/components/alert/style/css'
import 'element-plus/es/components/checkbox/style/css'
import 'element-plus/es/components/date-picker/style/css'
import 'element-plus/es/components/empty/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/radio/style/css'
import { Clock, Delete, DocumentCopy, Edit, FolderDelete, Promotion, Refresh, UploadFilled, VideoPlay } from '@element-plus/icons-vue'
import ContentCard from '../components/ContentCard.vue'
import { archiveContent, deleteContentLocal, getContent, getContents, type ContentItem } from '../api/content'
import { deleteMedia, getContentMedia, uploadMedia, type MediaAsset } from '../api/media'
import { extractPublication, waitForJobResult } from '../api/jobs'
import {
  getContentPublications,
  getXiaohongshuLoginStatus,
  publishToXiaohongshu,
  scheduleXiaohongshuPublication,
  type Publication,
  type XiaohongshuLoginStatus
} from '../api/publish'
import { CONTENT_TYPE_OPTIONS, getContentTypeLabel, getStatusLabel, getStyleLabel } from '../constants/content'

const router = useRouter()

const filters = reactive({ content_type: '', status: '' })
const query = ref('')
const items = ref<ContentItem[]>([])
const loading = ref(false)
const selected = ref<ContentItem>()
const mediaAssets = ref<MediaAsset[]>([])
const publications = ref<Publication[]>([])
const loginStatus = ref<XiaohongshuLoginStatus>()
const uploadingImages = ref(false)
const uploadingVideo = ref(false)
const publishingNow = ref(false)
const schedulingPublish = ref(false)
const isBulkArchiving = ref(false)
const isBulkDeleting = ref(false)
const selectionMode = ref(false)
const selectedIds = ref<number[]>([])
const publishForm = reactive({
  publish_type: 'image_post' as 'image_post' | 'video_post',
  title: '',
  content: '',
  scheduled_at: ''
})

const filteredItems = computed(() => {
  const term = query.value.trim().toLowerCase()
  if (!term) return items.value
  return items.value.filter(item => [item.title ?? '', item.content].join(' ').toLowerCase().includes(term))
})

const filteredItemIds = computed(() => filteredItems.value.map(item => item.id))
const imageAssets = computed(() => mediaAssets.value.filter(asset => asset.media_type === 'image'))
const videoAssets = computed(() => mediaAssets.value.filter(asset => asset.media_type === 'video'))
const allVisibleSelected = computed(() => filteredItems.value.length > 0 && filteredItems.value.every(item => selectedIds.value.includes(item.id)))

const loginStatusLabel = computed(() => {
  if (!loginStatus.value) return '登录状态未检测'
  return loginStatus.value.connected ? 'MCP 已登录' : 'MCP 未登录'
})

const publishHint = computed(() => {
  if (!selected.value) return ''
  if (!loginStatus.value?.connected) return '当前未检测到小红书 MCP 登录状态，发布可能失败。'
  if (publishForm.publish_type === 'image_post' && !imageAssets.value.length) {
    return '图文发布至少需要 1 张图片。'
  }
  if (publishForm.publish_type === 'video_post' && videoAssets.value.length !== 1) {
    return '视频发布需要且只允许 1 个视频。'
  }
  return ''
})

const canPublishNow = computed(() => Boolean(selected.value) && !publishHint.value && !selectionMode.value)
const canSchedulePublish = computed(() => Boolean(selected.value) && !publishHint.value && Boolean(publishForm.scheduled_at) && !selectionMode.value)

watch(filteredItemIds, ids => {
  const allowed = new Set(ids)
  selectedIds.value = selectedIds.value.filter(id => allowed.has(id))
})

async function load() {
  loading.value = true
  try {
    items.value = await getContents({
      limit: 100,
      content_type: filters.content_type || undefined,
      status: filters.status || undefined
    })
    if (selected.value) {
      const stillExists = items.value.find(item => item.id === selected.value?.id)
      if (stillExists && filteredItems.value.some(item => item.id === selected.value?.id)) {
        await open(stillExists.id)
      } else {
        resetDetail()
      }
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function open(id: number) {
  selected.value = await getContent(id)
  publishForm.title = selected.value.title || ''
  publishForm.content = ''
  publishForm.scheduled_at = ''
  await Promise.all([loadMedia(id), loadPublications(id), loadLoginStatus()])
}

function handleCardClick(id: number) {
  if (selectionMode.value) {
    setSelected(id, !isSelected(id))
    return
  }
  void open(id)
}

function resetDetail() {
  selected.value = undefined
  mediaAssets.value = []
  publications.value = []
  publishForm.title = ''
  publishForm.content = ''
  publishForm.scheduled_at = ''
}

function enterSelectionMode() {
  selectionMode.value = true
}

function exitSelectionMode() {
  selectionMode.value = false
  clearSelection()
}

function clearSelection() {
  selectedIds.value = []
}

function isSelected(id: number) {
  return selectedIds.value.includes(id)
}

function setSelected(id: number, checked: boolean) {
  if (checked) {
    if (!selectedIds.value.includes(id)) {
      selectedIds.value = [...selectedIds.value, id]
    }
    return
  }
  selectedIds.value = selectedIds.value.filter(currentId => currentId !== id)
}

function onSelectionChange(id: number, value: string | number | boolean) {
  setSelected(id, Boolean(value))
}

function toggleSelectAllVisible() {
  if (allVisibleSelected.value) {
    clearSelection()
    return
  }
  selectedIds.value = filteredItems.value.map(item => item.id)
}

async function loadMedia(contentId: number) {
  mediaAssets.value = await getContentMedia(contentId)
}

async function loadPublications(contentId: number) {
  publications.value = await getContentPublications(contentId)
}

async function loadLoginStatus() {
  try {
    loginStatus.value = await getXiaohongshuLoginStatus()
  } catch (error) {
    loginStatus.value = {
      connected: false,
      status_text: (error as Error).message
    }
  }
}

function goRefine() {
  if (!selected.value) return
  void router.push({ path: '/refine', query: { id: String(selected.value.id) } })
}

async function copyContent() {
  if (!selected.value?.content) return
  try {
    await navigator.clipboard.writeText(selected.value.content)
    ElMessage.success('已复制内容')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

async function onImageFilesSelected(event: Event) {
  const files = Array.from((event.target as HTMLInputElement).files || [])
  if (!selected.value || !files.length) return
  uploadingImages.value = true
  try {
    for (const file of files) {
      await uploadMedia(selected.value.id, 'image', file)
    }
    await loadMedia(selected.value.id)
    ElMessage.success('图片上传完成')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    uploadingImages.value = false
    ;(event.target as HTMLInputElement).value = ''
  }
}

async function onVideoFileSelected(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!selected.value || !file) return
  uploadingVideo.value = true
  try {
    await uploadMedia(selected.value.id, 'video', file)
    await loadMedia(selected.value.id)
    ElMessage.success('视频上传完成')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    uploadingVideo.value = false
    ;(event.target as HTMLInputElement).value = ''
  }
}

async function removeMedia(mediaId: number) {
  if (!selected.value) return
  try {
    await deleteMedia(mediaId)
    await loadMedia(selected.value.id)
    ElMessage.success('素材已删除')
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function publishNow() {
  if (!selected.value || !canPublishNow.value) return
  publishingNow.value = true
  try {
    const action = await publishToXiaohongshu({
      content_id: selected.value.id,
      publish_type: publishForm.publish_type,
      title: publishForm.title || undefined,
      content: publishForm.content || undefined
    })
    await waitForJobResult(action.job_id, extractPublication)
    await refreshSelectedData(selected.value.id)
    ElMessage.success('发布任务已完成')
  } catch (error) {
    ElMessage.error((error as Error).message)
    if (selected.value) await loadPublications(selected.value.id)
  } finally {
    publishingNow.value = false
  }
}

async function schedulePublish() {
  if (!selected.value || !canSchedulePublish.value) return
  schedulingPublish.value = true
  try {
    const action = await scheduleXiaohongshuPublication({
      content_id: selected.value.id,
      publish_type: publishForm.publish_type,
      title: publishForm.title || undefined,
      content: publishForm.content || undefined,
      scheduled_at: publishForm.scheduled_at
    })
    await waitForJobResult(action.job_id, extractPublication)
    await refreshSelectedData(selected.value.id)
    ElMessage.success('定时发布已提交')
  } catch (error) {
    ElMessage.error((error as Error).message)
    if (selected.value) await loadPublications(selected.value.id)
  } finally {
    schedulingPublish.value = false
  }
}

async function archiveSelectedSingle() {
  if (!selected.value) return
  await archiveItems([selected.value.id], '当前内容')
}

async function deleteSelectedSingle() {
  if (!selected.value) return
  await deleteItems([selected.value.id], '当前内容')
}

async function archiveSelectedBatch() {
  if (!selectedIds.value.length) return
  await archiveItems([...selectedIds.value], `${selectedIds.value.length} 条内容`, true)
}

async function deleteSelectedBatch() {
  if (!selectedIds.value.length) return
  await deleteItems([...selectedIds.value], `${selectedIds.value.length} 条内容`, true)
}

async function archiveItems(ids: number[], label: string, bulk = false) {
  try {
    await ElMessageBox.confirm(
      `${bulk ? '批量归档' : '归档'}后内容仍会保留在本地数据库中，只是状态会变成“已归档”。`,
      `归档${label}`,
      { type: 'warning', confirmButtonText: '归档', cancelButtonText: '取消' }
    )
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error((error as Error).message)
    }
    return
  }

  isBulkArchiving.value = bulk
  let success = 0
  let failed = 0
  const currentSelectedId = selected.value?.id
  try {
    for (const id of ids) {
      try {
        await archiveContent(id)
        success += 1
      } catch {
        failed += 1
      }
    }
    exitSelectionMode()
    await load()
    if (currentSelectedId && !ids.includes(currentSelectedId)) {
      await refreshSelectedData(currentSelectedId)
    } else if (currentSelectedId && !filteredItems.value.some(item => item.id === currentSelectedId)) {
      resetDetail()
    }
    if (failed) {
      ElMessage.warning(`已归档 ${success} 条，失败 ${failed} 条`)
    } else {
      ElMessage.success(`已归档 ${success} 条`)
    }
  } finally {
    isBulkArchiving.value = false
  }
}

async function deleteItems(ids: number[], label: string, bulk = false) {
  const selectedCandidates = items.value.filter(item => ids.includes(item.id))
  const publishedLike = selectedCandidates.some(item => ['published', 'scheduled'].includes(item.status))
  const message = publishedLike
    ? '这会删除本地内容、本地素材、发布记录和日历记录，但不会删除小红书线上帖子。是否继续？'
    : '这会删除本地内容以及相关素材和记录。是否继续？'

  try {
    await ElMessageBox.confirm(message, `删除${label}`, {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      confirmButtonClass: 'el-button--danger'
    })
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error((error as Error).message)
    }
    return
  }

  isBulkDeleting.value = bulk
  let success = 0
  let failed = 0
  const currentSelectedId = selected.value?.id
  try {
    for (const id of ids) {
      try {
        await deleteContentLocal(id)
        success += 1
      } catch {
        failed += 1
      }
    }
    exitSelectionMode()
    await load()
    if (currentSelectedId && !ids.includes(currentSelectedId)) {
      await refreshSelectedData(currentSelectedId)
    } else {
      resetDetail()
    }
    if (failed) {
      ElMessage.warning(`已删除 ${success} 条，失败 ${failed} 条`)
    } else {
      ElMessage.success(`已删除 ${success} 条`)
    }
  } finally {
    isBulkDeleting.value = false
  }
}

async function refreshSelectedData(contentId: number) {
  await load()
  const stillExists = items.value.find(item => item.id === contentId)
  if (!stillExists || !filteredItems.value.some(item => item.id === contentId)) {
    resetDetail()
    return
  }
  selected.value = await getContent(contentId)
  await Promise.all([loadMedia(contentId), loadPublications(contentId), loadLoginStatus()])
}

function formatDate(value?: string) {
  if (!value) return '-'
  return value.replace('T', ' ').slice(0, 16)
}

onMounted(async () => {
  await load()
  await loadLoginStatus()
})
</script>

<style scoped>
.history-page {
  display: grid;
  gap: 20px;
  padding: 24px 32px;
  background: var(--c-bg);
}

.history-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.hero-kicker,
.section-kicker {
  display: inline-block;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.history-hero .page-title {
  margin-top: 6px;
  font-size: var(--fs-h1);
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1.15;
}

.history-hero .page-subtitle {
  color: var(--c-text-secondary);
  font-size: 14px;
}

.filter-section {
  padding: 16px 20px;
}

.filter-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) repeat(2, minmax(180px, 220px)) auto;
  gap: 12px;
}

.results-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(420px, 0.95fr);
  gap: 16px;
  align-items: start;
}

.list-section,
.detail-section {
  padding: 20px;
  max-height: calc(100vh - 240px);
  min-height: 480px;
  display: flex;
  flex-direction: column;
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.section-head h2,
.block-head h3 {
  margin: 4px 0 0;
  color: var(--c-text);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0;
}

.list-actions,
.selection-actions,
.detail-actions,
.upload-actions,
.publish-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.section-pill {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border: 1px solid var(--c-border);
  border-radius: 999px;
  color: var(--c-text-secondary);
  background: var(--c-surface);
  font-size: 11px;
  font-family: var(--font-mono);
  letter-spacing: 0;
}

.selection-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px 14px;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  background: var(--c-bg-soft);
}

.selection-copy {
  display: grid;
  gap: 2px;
}

.selection-copy strong {
  color: var(--c-text);
  font-size: 13px;
  font-weight: 600;
}

.selection-copy span {
  color: var(--c-text-tertiary);
  font-size: 11.5px;
  font-family: var(--font-mono);
}

.library-grid,
.detail-shell,
.publication-list {
  display: grid;
  gap: 12px;
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.library-grid::-webkit-scrollbar,
.detail-shell::-webkit-scrollbar,
.publication-list::-webkit-scrollbar {
  width: 8px;
}

.library-grid::-webkit-scrollbar-thumb,
.detail-shell::-webkit-scrollbar-thumb,
.publication-list::-webkit-scrollbar-thumb {
  background: var(--c-border);
  border-radius: 4px;
}

.library-grid::-webkit-scrollbar-thumb:hover,
.detail-shell::-webkit-scrollbar-thumb:hover,
.publication-list::-webkit-scrollbar-thumb:hover {
  background: var(--c-text-tertiary);
}

.library-entry {
  position: relative;
}

.library-entry.selectable .library-card {
  cursor: pointer;
}

.library-entry.selected :deep(.content-card) {
  border-color: var(--c-accent);
  box-shadow: 0 0 0 1px var(--c-accent);
}

.card-checkbox {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 4px;
  background: var(--c-surface);
  border: 1px solid var(--c-border);
}

.library-card {
  width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.detail-meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.meta-card,
.detail-block,
.publication-card {
  padding: 14px;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  background: var(--c-surface);
}

.meta-card {
  background: var(--c-bg-soft);
}

.meta-card span,
.field span {
  display: block;
  color: var(--c-text-tertiary);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.meta-card strong {
  display: block;
  margin-top: 4px;
  color: var(--c-text);
  font-size: 13px;
  font-weight: 500;
  font-family: var(--font-mono);
}

.content-preview {
  padding: 16px;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  background: var(--c-surface);
  color: var(--c-text);
  font-size: 13.5px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.block-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.upload-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  background: var(--c-surface);
  color: var(--c-text);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: border-color 100ms ease;
}

.upload-trigger:hover {
  border-color: var(--c-border-strong);
}

.hidden-input {
  display: none;
}

.media-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}

.media-card {
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  background: var(--c-surface);
}

.media-preview {
  overflow: hidden;
  border-radius: 4px;
  background: var(--c-bg-code);
}

.media-preview img,
.media-preview video {
  display: block;
  width: 100%;
  max-height: 180px;
  object-fit: cover;
}

.media-copy {
  display: grid;
  gap: 2px;
}

.media-copy strong {
  color: var(--c-text);
  font-size: 13px;
  font-weight: 500;
  font-family: var(--font-mono);
  word-break: break-word;
}

.media-copy span,
.publication-card small {
  color: var(--c-text-tertiary);
  font-size: 11.5px;
  font-family: var(--font-mono);
}

.publish-panel {
  display: grid;
  gap: 12px;
}

.publish-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.field {
  display: grid;
  gap: 6px;
}

.field-wide {
  grid-column: 1 / -1;
}

.login-badge {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border: 1px solid var(--c-ok);
  border-radius: 999px;
  color: var(--c-ok);
  background: var(--c-ok-soft);
  font-size: 11px;
  font-weight: 500;
  font-family: var(--font-mono);
  letter-spacing: 0;
}

.login-badge.offline {
  color: var(--c-fail);
  border-color: var(--c-fail);
  background: var(--c-fail-soft);
}

.publication-topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}

.publication-topline strong {
  color: var(--c-text);
  font-size: 13px;
  font-weight: 600;
}

.publication-topline span {
  color: var(--c-text-secondary);
  font-size: 11.5px;
  font-family: var(--font-mono);
}

.publication-card p {
  margin: 0 0 6px;
  color: var(--c-text);
  font-size: 13px;
  line-height: 1.55;
}

.error-copy {
  color: var(--c-fail) !important;
}

@media (max-width: 1120px) {
  .history-page {
    padding: 16px;
  }

  .results-grid,
  .publish-grid {
    grid-template-columns: 1fr;
  }

  .filter-grid {
    grid-template-columns: 1fr;
  }

  .selection-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
