const byId = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatJson(value) {
  return escapeHtml(JSON.stringify(value ?? {}, null, 2));
}

function renderLoading(message) {
  return `<div class="summary-card"><p>${escapeHtml(message)}</p></div>`;
}

async function readErrorMessage(response) {
  const text = await response.text();
  if (!text) {
    return "请求失败";
  }
  try {
    const parsed = JSON.parse(text);
    return parsed.detail || text;
  } catch {
    return text;
  }
}

function renderChips(values) {
  if (!values?.length) {
    return '<span class="pill">当前未传入模块</span>';
  }
  return values.map((value) => `<span class="pill">${escapeHtml(value)}</span>`).join("");
}

function renderFieldRows(items, type) {
  if (!items?.length) {
    return "";
  }
  const nameKey = type === "segment" ? "segment" : "field";
  const targetKey = type === "segment" ? "derived_from" : "preprocessed_targets";

  return `
    <div class="table-wrap">
      <table class="debug-table">
        <thead>
          <tr>
            <th>标签</th>
            <th>说明</th>
            <th>值预览</th>
            <th>${type === "segment" ? "来源字段" : "预处理去向"}</th>
            <th>后续模块</th>
          </tr>
        </thead>
        <tbody>
          ${items
            .map(
              (item) => `
                <tr>
                  <td>
                    <strong>${escapeHtml(item.label || item[nameKey])}</strong>
                    <div class="subtle">${escapeHtml(item[nameKey])}</div>
                  </td>
                  <td>${escapeHtml(item.notes || item.display_name || "")}</td>
                  <td><pre class="mini-code">${formatJson(item.value_preview)}</pre></td>
                  <td>${renderChips(item[targetKey] || [])}</td>
                  <td>${renderChips(item.modules || [])}</td>
                </tr>
              `
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderMetadataRows(items) {
  if (!items?.length) {
    return "";
  }
  return `
    <div class="table-wrap">
      <table class="debug-table">
        <thead>
          <tr>
            <th>metadata 键</th>
            <th>当前值</th>
            <th>使用模块</th>
          </tr>
        </thead>
        <tbody>
          ${items
            .map(
              (item) => `
                <tr>
                  <td><strong>${escapeHtml(item.key)}</strong></td>
                  <td><pre class="mini-code">${formatJson(item.value)}</pre></td>
                  <td>${renderChips(item.modules || [])}</td>
                </tr>
              `
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderModuleRoutes(items) {
  if (!items?.length) {
    return "";
  }
  return `
    <div class="debug-card-grid">
      ${items
        .map(
          (item) => `
            <article class="summary-card">
              <div class="summary-top">
                <h3>${escapeHtml(item.module_name)}</h3>
                <span class="pill">${escapeHtml(item.module_id)}</span>
              </div>
              <p>${escapeHtml(item.notes || item.detection_goal || "")}</p>
              <div class="debug-stack">
                <div>
                  <strong>直接接收的原始字段</strong>
                  <div class="meta">${renderChips(item.raw_fields || [])}</div>
                </div>
                <div>
                  <strong>使用的预处理分段</strong>
                  <div class="meta">${renderChips(item.preprocessed_segments || [])}</div>
                </div>
                <div>
                  <strong>依赖的 metadata 键</strong>
                  <div class="meta">${renderChips(item.metadata_keys || [])}</div>
                </div>
              </div>
            </article>
          `
        )
        .join("")}
    </div>
  `;
}

function renderSummary(data) {
  const source = data.source || {};
  const payload = data.raw_collected?.input_payload || {};
  const processing = source.video_processing || {};

  byId("trace-summary").classList.remove("empty");
  byId("trace-summary").innerHTML = `
    <article class="summary-card">
      <div class="summary-top">
        <h3>${escapeHtml(payload.title || source.title || "当前样本")}</h3>
        <span class="pill">${escapeHtml(source.platform || "unknown")}</span>
      </div>
      <p>${escapeHtml(payload.description || source.desc || "暂无描述")}</p>
      <div class="meta">
        <span class="pill">视频编号 ${escapeHtml(payload.video_id || source.aweme_id || "-")}</span>
        <span class="pill">作者 ${escapeHtml(source.author_nickname || payload.metadata?.author_nickname || "-")}</span>
        <span class="pill">候选评论 ${escapeHtml(source.comment_count_scanned || 0)}</span>
        <span class="pill">重要评论 ${escapeHtml(source.comment_count_fetched || 0)}</span>
        <span class="pill">OCR ${escapeHtml(payload.ocr_text?.length || 0)}</span>
        <span class="pill">音频线索 ${escapeHtml(payload.audio_cues?.length || 0)}</span>
        ${
          source.video_processing
            ? `
              <span class="pill">抽帧 ${escapeHtml(processing.extracted_frame_count || 0)}</span>
              <span class="pill">ASR ${escapeHtml(processing.asr_backend || "-")}</span>
              <span class="pill">语音来源 ${escapeHtml(processing.speech_source || "-")}</span>
            `
            : ""
        }
      </div>
    </article>
  `;
}

function renderDetail(data) {
  const rawCollected = data.raw_collected || {};
  const preprocessed = data.preprocessed || {};

  byId("trace-detail").classList.remove("empty");
  byId("trace-detail").innerHTML = `
    <article class="summary-card">
      <div class="summary-top">
        <h3>原始采集字段</h3>
      </div>
      <p>这一层是抓取和视频处理结束后，统一写入 <code>AnalysisInput</code> 的字段。</p>
      ${renderFieldRows(rawCollected.field_trace || [], "field")}
    </article>

    <article class="summary-card">
      <div class="summary-top">
        <h3>预处理结果</h3>
      </div>
      <p>这一层是进入各独立模块之前的标准化分段和元数据。</p>
      ${renderFieldRows(preprocessed.segment_trace || [], "segment")}
    </article>

    <article class="summary-card">
      <div class="summary-top">
        <h3>metadata 去向</h3>
      </div>
      <p>这里只列出当前真实被后续模块关注的标准化 metadata 键。</p>
      ${renderMetadataRows(preprocessed.metadata_trace || [])}
    </article>

    <article class="summary-card">
      <div class="summary-top">
        <h3>模块输入路线</h3>
      </div>
      <p>这一层按模块反向看它们各自实际接收什么。</p>
      ${renderModuleRoutes(data.module_routes || [])}
    </article>

    <article class="summary-card">
      <div class="summary-top">
        <h3>完整 JSON</h3>
      </div>
      <div class="debug-card-grid">
        <article class="summary-card">
          <div class="summary-top">
            <h3>source_summary</h3>
          </div>
          <pre class="code-block">${formatJson(rawCollected.source_summary || {})}</pre>
        </article>
        <article class="summary-card">
          <div class="summary-top">
            <h3>input_payload</h3>
          </div>
          <pre class="code-block">${formatJson(rawCollected.input_payload || {})}</pre>
        </article>
        <article class="summary-card">
          <div class="summary-top">
            <h3>normalized_segments</h3>
          </div>
          <pre class="code-block">${formatJson(preprocessed.normalized_segments || {})}</pre>
        </article>
        <article class="summary-card">
          <div class="summary-top">
            <h3>standardized_metadata</h3>
          </div>
          <pre class="code-block">${formatJson(preprocessed.standardized_metadata || {})}</pre>
        </article>
      </div>
    </article>
  `;
}

async function submitTrace(event) {
  event.preventDefault();
  byId("trace-summary").innerHTML = renderLoading("正在抓取链接并生成数据流检查结果...");
  byId("trace-summary").classList.remove("empty");
  byId("trace-detail").innerHTML = renderLoading("正在整理原始字段、预处理分段和模块去向...");
  byId("trace-detail").classList.remove("empty");

  try {
    const response = await fetch("/api/v1/debug/flow", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_url: byId("source_url").value.trim(),
        max_comments: Number(byId("max_comments").value || 20),
        comment_selection_mode: byId("comment_selection_mode").value || "comprehensive",
        process_video: byId("process_video").checked,
        frame_interval_seconds: Number(byId("frame_interval_seconds").value || 4),
        max_frames: Number(byId("max_frames").value || 6),
        asr_model_path: byId("asr_model_path").value.trim() || null
      })
    });

    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }

    const data = await response.json();
    renderSummary(data);
    renderDetail(data);
  } catch (error) {
    const message = escapeHtml(String(error.message || error));
    byId("trace-summary").innerHTML = `<div class="summary-card"><p>抓取失败：${message}</p></div>`;
    byId("trace-detail").innerHTML = `<div class="summary-card"><p>生成检查结果失败：${message}</p></div>`;
  }
}

byId("trace-form").addEventListener("submit", submitTrace);
