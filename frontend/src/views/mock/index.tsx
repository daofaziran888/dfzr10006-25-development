import { useCallback, useEffect, useMemo, useState } from 'react'

import { request } from '@/api/client'

const ENDPOINT = '/api/mock'
const columns = [
  "配置编号",
  "模拟对象",
  "数据模板",
  "模板格式",
  "生成条数",
  "字段规则",
  "响应延迟",
  "错误概率",
  "配置状态"
]
const actions = [
  "启用模拟",
  "暂停模拟",
  "关闭模拟"
]
const batchColumns = [
  "批次编号",
  "配置编号",
  "模拟对象",
  "数据模板",
  "生成条数",
  "实际条数",
  "批次状态",
  "生成时间"
]
const batchFilterFields = ["数据模板", "模拟对象", "批次编号"]

type Row = Record<string, any>

function RecordsTable({ records }: { records: Row[] }) {
  const keys = useMemo(() => {
    const all: string[] = []
    records.forEach((record) => {
      Object.keys(record).forEach((key) => {
        if (!all.includes(key)) all.push(key)
      })
    })
    return all
  }, [records])
  if (records.length === 0) {
    return <p className="empty-state">该批次暂无模拟数据记录</p>
  }
  return (
    <table className="data-table">
      <thead>
        <tr>{keys.map((key) => <th key={key}>{key}</th>)}</tr>
      </thead>
      <tbody>
        {records.map((record, index) => (
          <tr key={index}>
            {keys.map((key) => <td key={key}>{String(record[key] ?? '—')}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function MockView() {
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [errorMessage, setErrorMessage] = useState('')
  const [infoMessage, setInfoMessage] = useState('')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const filterFields = useMemo(() => columns.slice(0, 3), [])

  const [batches, setBatches] = useState<Row[]>([])
  const [batchTotal, setBatchTotal] = useState(0)
  const [batchFilters, setBatchFilters] = useState<Record<string, string>>({})
  const [batchStats, setBatchStats] = useState({ valid: 0, history: 0 })
  const [batchDetail, setBatchDetail] = useState<Row | null>(null)
  const [responseView, setResponseView] = useState<Row | null>(null)

  const reload = useCallback(async () => {
    setErrorMessage('')
    const query = new URLSearchParams(filters).toString()
    try {
      const response = await request(`${ENDPOINT}?${query}`)
      if (!response.ok) {
        throw new Error('模拟配置列表读取失败')
      }
      const payload = await response.json()
      setRows(payload.items ?? [])
      setTotal(payload.total ?? 0)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '数据模拟服务列表读取失败')
    }
  }, [filters])

  const reloadBatches = useCallback(async () => {
    const query = new URLSearchParams(batchFilters).toString()
    try {
      const response = await request(`${ENDPOINT}/batches?${query}`)
      if (!response.ok) {
        throw new Error('模拟批次列表读取失败')
      }
      const payload = await response.json()
      setBatches(payload.items ?? [])
      setBatchTotal(payload.total ?? 0)
      const statsResponse = await request(`${ENDPOINT}/batches?size=200`)
      if (statsResponse.ok) {
        const statsPayload = await statsResponse.json()
        const all: Row[] = statsPayload.items ?? []
        setBatchStats({
          valid: all.filter((item) => item['批次状态'] === '有效').length,
          history: all.filter((item) => item['批次状态'] === '历史').length,
        })
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '模拟批次列表读取失败')
    }
  }, [batchFilters])

  useEffect(() => {
    void reload()
  }, [reload])

  useEffect(() => {
    void reloadBatches()
  }, [reloadBatches])

  async function runAction(action: string, row: Row) {
    setErrorMessage('')
    setInfoMessage('')
    try {
      const response = await request(`${ENDPOINT}/${row.id}/actions`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      })
      if (!response.ok) {
        throw new Error('数据模拟服务动作未生效，请稍后重试')
      }
      await reload()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '数据模拟服务操作失败')
    }
  }

  async function generateBatch(row: Row) {
    setErrorMessage('')
    setInfoMessage('')
    try {
      const response = await request(`${ENDPOINT}/${row.id}/generate`, {
        method: 'POST',
        body: JSON.stringify({ values: {} }),
      })
      const payload = await response.json()
      if (!response.ok || !payload.ok) {
        throw new Error(payload.message ?? payload.detail ?? '生成模拟数据失败')
      }
      setInfoMessage(payload.message)
      await reloadBatches()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '生成模拟数据失败')
    }
  }

  async function showResponse(row: Row) {
    setErrorMessage('')
    setInfoMessage('')
    setResponseView(null)
    try {
      const response = await request(`${ENDPOINT}/${row.id}/response`)
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.detail ?? '当前模拟响应读取失败')
      }
      setResponseView(payload)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '当前模拟响应读取失败')
    }
  }

  async function showBatchDetail(batch: Row) {
    setErrorMessage('')
    try {
      const response = await request(`${ENDPOINT}/batches/${encodeURIComponent(batch['批次编号'])}`)
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.detail ?? '批次明细读取失败')
      }
      setBatchDetail(payload)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '批次明细读取失败')
    }
  }

  const stats = [
    { label: '模拟配置总数', value: total },
    { label: '有效批次', value: batchStats.valid },
    { label: '历史批次', value: batchStats.history },
  ]

  return (
    <section className="page" data-module="mock">
      <header className="page-head">
        <div>
          <h2>数据模拟服务管理</h2>
          <p className="page-desc">维护数据模拟的模板定义、生成规则与异常模拟，为服务联调测试提供可验证的数据工程流程。</p>
        </div>
        <div className="page-actions">
          <button className="btn primary" type="button" onClick={() => setErrorMessage('模拟配置登记入口尚未接入审批流')}>
            登记模拟配置
          </button>
          <button className="btn" type="button" onClick={() => window.open(`${ENDPOINT}/export`, '_blank')}>
            导出数据模拟服务清单
          </button>
        </div>
      </header>

      <div className="stat-row">
        {stats.map((item) => (
          <article key={item.label} className="stat-card">
            <span className="stat-label">{item.label}</span>
            <strong className="stat-value">{item.value}</strong>
          </article>
        ))}
      </div>

      <form className="filter-bar" onSubmit={(event) => { event.preventDefault(); void reload() }}>
        {filterFields.map((field) => (
          <label key={field} className="filter-item">
            <span>{field}</span>
            <input
              value={filters[field] ?? ''}
              placeholder={`按${field}检索`}
              onChange={(event) => setFilters((prev) => ({ ...prev, [field]: event.target.value }))}
            />
          </label>
        ))}
        <button className="btn" type="submit">查询</button>
        <button className="btn ghost" type="button" onClick={() => setFilters({})}>重置条件</button>
      </form>

      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => <th key={column}>{column}</th>)}
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={String(row.id)}>
              {columns.map((column) => <td key={column}>{row[column] ?? '—'}</td>)}
              <td className="row-actions">
                {actions.map((action) => (
                  <button key={action} className="link" type="button" onClick={() => void runAction(action, row)}>
                    {action}
                  </button>
                ))}
                <button className="link" type="button" onClick={() => void generateBatch(row)}>生成模拟数据</button>
                <button className="link" type="button" onClick={() => void showResponse(row)}>模拟响应</button>
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td className="empty-state" colSpan={columns.length + 1}>暂无数据模拟服务数据，可先登记模拟配置</td>
            </tr>
          )}
        </tbody>
      </table>

      <footer className="page-foot">
        <span>共 {total} 条数据模拟服务记录</span>
        {infoMessage && <span className="ok-text">{infoMessage}</span>}
        {errorMessage && <span className="error-text">{errorMessage}</span>}
      </footer>

      {responseView && (
        <div className="detail-panel">
          <h3>当前模拟响应（{responseView['配置编号']}）</h3>
          <div className="detail-meta">
            <span>模拟对象：{responseView['模拟对象']}</span>
            <span>数据模板：{responseView['数据模板']}</span>
            <span>引用批次：{responseView['批次编号']}（{responseView['批次状态']}）</span>
            <span>记录数：{responseView['记录数']}</span>
          </div>
          <RecordsTable records={responseView.records ?? []} />
        </div>
      )}

      <h3 className="section-title">模拟数据批次浏览</h3>
      <form className="filter-bar" onSubmit={(event) => { event.preventDefault(); void reloadBatches() }}>
        {batchFilterFields.map((field) => (
          <label key={field} className="filter-item">
            <span>{field}</span>
            <input
              value={batchFilters[field] ?? ''}
              placeholder={`按${field}检索`}
              onChange={(event) => setBatchFilters((prev) => ({ ...prev, [field]: event.target.value }))}
            />
          </label>
        ))}
        <button className="btn" type="submit">查询批次</button>
        <button className="btn ghost" type="button" onClick={() => setBatchFilters({})}>重置条件</button>
      </form>

      <table className="data-table">
        <thead>
          <tr>
            {batchColumns.map((column) => <th key={column}>{column}</th>)}
            <th>汇总核对</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {batches.map((batch) => (
            <tr key={String(batch['批次编号'])}>
              {batchColumns.map((column) => (
                <td key={column}>
                  {column === '批次状态' ? (
                    <span className={`tag ${batch[column] === '有效' ? 'current' : 'history'}`}>{batch[column]}</span>
                  ) : (
                    batch[column] ?? '—'
                  )}
                </td>
              ))}
              <td>{batch['汇总一致'] ? '一致' : '不一致'}</td>
              <td className="row-actions">
                <button className="link" type="button" onClick={() => void showBatchDetail(batch)}>查看数据</button>
              </td>
            </tr>
          ))}
          {batches.length === 0 && (
            <tr>
              <td className="empty-state" colSpan={batchColumns.length + 2}>暂无模拟批次，可先在配置行点击「生成模拟数据」</td>
            </tr>
          )}
        </tbody>
      </table>

      <footer className="page-foot">
        <span>共 {batchTotal} 个模拟数据批次</span>
      </footer>

      {batchDetail && (
        <div className="detail-panel">
          <h3>批次明细（{batchDetail['批次编号']}）</h3>
          <div className="detail-meta">
            <span>配置编号：{batchDetail['配置编号']}</span>
            <span>模拟对象：{batchDetail['模拟对象']}</span>
            <span>数据模板：{batchDetail['数据模板']}</span>
            <span>批次状态：{batchDetail['批次状态']}</span>
            <span>生成条数：{batchDetail['生成条数']} / 实际条数：{batchDetail['实际条数']}</span>
          </div>
          <div className="detail-meta">
            <span>字段规则：{batchDetail['字段规则']}</span>
          </div>
          <RecordsTable records={batchDetail.records ?? []} />
        </div>
      )}
    </section>
  )
}
