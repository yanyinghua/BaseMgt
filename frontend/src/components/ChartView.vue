<template>
  <div ref="box" style="width: 100%; height: 300px"></div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  type: { type: String, default: 'bar' }, // bar | line | pie
  data: { type: Array, default: () => [] }, // [{name, value}]
  height: { type: Number, default: 300 }
})

const box = ref(null)
let chart = null

const build = () => {
  if (!chart) return
  const items = props.data || []
  if (props.type === 'pie') {
    chart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { bottom: 0, type: 'scroll' },
      series: [{
        type: 'pie', radius: ['38%', '66%'],
        label: { formatter: '{b}\n{d}%' },
        data: items
      }]
    }, true)
    return
  }
  const rotate = items.length > 6 ? 30 : 0
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 20, bottom: rotate ? 70 : 40 },
    xAxis: { type: 'category', data: items.map((i) => i.name), axisLabel: { rotate, interval: 0 } },
    yAxis: { type: 'value' },
    series: [{
      type: props.type,
      data: items.map((i) => i.value),
      itemStyle: { color: '#409eff' },
      smooth: props.type === 'line'
    }]
  }, true)
}

const resize = () => chart && chart.resize()

onMounted(() => {
  box.value.style.height = `${props.height}px`
  chart = echarts.init(box.value)
  build()
  window.addEventListener('resize', resize)
})

watch(() => [props.data, props.type], build, { deep: true })

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart && chart.dispose()
})
</script>
