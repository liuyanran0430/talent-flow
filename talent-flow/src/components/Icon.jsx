import { Icon as IconifyIcon } from '@iconify/react'

/**
 * 轻量封装 @iconify/react，对齐原型中 <iconify-icon icon="..." width="..."/> 的用法。
 */
export default function Icon({ icon, width, className, style, ...rest }) {
  return (
    <IconifyIcon
      icon={icon}
      width={width}
      className={className}
      style={style}
      {...rest}
    />
  )
}
