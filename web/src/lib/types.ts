export type BandEnergySeries = {
  times_s: number[]
  energy: number[]
}

export type ReportFile = {
  file: string
  recorded_at: string | null
  duration_s: number
  n_events: number
  max_simultaneous: number
  threshold: number
  spectrogram: string
  band_energy: BandEnergySeries
}

export type ReportEvent = {
  file: string
  recorded_at: string | null
  event: number
  start_s: number
  end_s: number
  peak_time_s: number
  peak_freq_hz: number
  energy: number
  n_callers: number
  duration_s: number
}

export type HourBucket = {
  hour: number
  n_events: number
}

export type MonthBucket = {
  month: number
  n_events: number
}

export type DetectionReport = {
  generated_at: string
  species: string
  common_name: string
  config: {
    sample_rate: number
    lowcut_hz: number
    highcut_hz: number
    threshold_k: number
  }
  summary: {
    n_files: number
    n_events: number
    max_simultaneous: number
    total_duration_s: number
  }
  files: ReportFile[]
  events: ReportEvent[]
  by_hour: HourBucket[]
  by_month: MonthBucket[]
}
