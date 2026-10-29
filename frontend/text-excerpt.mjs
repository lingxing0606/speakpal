// 打印渲染出来的可见文字，作为「页面确实渲染出了内容」的证据
import fs from 'node:fs'

const file = process.argv[2]
const html = fs.readFileSync(file, 'utf8')
const text = html
  .replace(/<style[\s\S]*?<\/style>/gi, '')
  .replace(/<[^>]+>/g, '\n')
  .split('\n')
  .map((s) => s.trim())
  .filter(Boolean)
console.log(text.join(' | '))
