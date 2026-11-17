// 每个页面各自渲染页头，切页时页头会重新挂载；
// 这个模块作用域（不随组件销毁）记住上一次黑块的位置，新页头从那里滑到当前项。
export interface HeaderIndicator {
  index: number
  x: number
  w: number
}

export const headerIndicator: { last: HeaderIndicator | null } = { last: null }
