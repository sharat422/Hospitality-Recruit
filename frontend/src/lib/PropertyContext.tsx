import React,{ createContext,useCallback,useContext,useEffect,useMemo,useState } from 'react'
import { apiClient } from './api'
import { useAuth } from './AuthContext'

export interface HotelProperty {
  id: string
  name: string
  code?: string | null
  type: string
  city?: string | null
  state?: string | null
  country?: string | null
  logo_url?: string | null
  brand_color?: string | null
  star_rating?: number | null
  membership?: { role: string; is_default: boolean }
}

interface PropertyContextValue {
  properties: HotelProperty[]
  activeProperty: HotelProperty | null
  loading: boolean
  error: string | null
  refreshProperties: () => Promise<void>
  switchProperty: (propertyId: string) => Promise<void>
}

const PropertyContext = createContext<PropertyContextValue | undefined>(undefined)

export function PropertyProvider({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth()
  const [properties, setProperties] = useState<HotelProperty[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refreshProperties = useCallback(async () => {
    if (!isAuthenticated) {
      setProperties([])
      setActiveId(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const { data } = await apiClient.get('/hotels/properties')
      const rows: HotelProperty[] = data.properties ?? []
      setProperties(rows)
      const nextId = data.active_property_id ?? rows[0]?.id ?? null
      setActiveId(nextId)
      if (nextId) localStorage.setItem('hosprecruit.activePropertyId', nextId)
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'Unable to load properties.')
    } finally {
      setLoading(false)
    }
  }, [isAuthenticated])

  useEffect(() => { void refreshProperties() }, [refreshProperties])

  const switchProperty = useCallback(async (propertyId: string) => {
    const previous = activeId
    setActiveId(propertyId)
    localStorage.setItem('hosprecruit.activePropertyId', propertyId)
    try {
      await apiClient.post(`/hotels/properties/${propertyId}/switch`)
    } catch (err) {
      setActiveId(previous)
      if (previous) localStorage.setItem('hosprecruit.activePropertyId', previous)
      throw err
    }
  }, [activeId])

  const activeProperty = useMemo(
    () => properties.find(property => property.id === activeId) ?? properties[0] ?? null,
    [properties, activeId],
  )

  return (
    <PropertyContext.Provider value={{ properties, activeProperty, loading, error, refreshProperties, switchProperty }}>
      {children}
    </PropertyContext.Provider>
  )
}

export function useProperty() {
  const context = useContext(PropertyContext)
  if (!context) throw new Error('useProperty must be used within PropertyProvider')
  return context
}
