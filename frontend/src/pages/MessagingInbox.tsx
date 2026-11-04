import { apiClient } from '@/lib/api'
import { MessageSquare,Send } from 'lucide-react'
import React,{ useEffect,useRef,useState } from 'react'

interface Candidate {
  name?: string
  full_name?: string
  email?: string
}

interface JobRole {
  title?: string
}

interface Message {
  id: string
  sender_type: string
  body: string
  sent_at: string
  status: string
  read_at?: string
  channel: string
}

interface Conversation {
  id: string
  candidate_id: string
  job_role_id?: string
  channel: string
  status: string
  last_message_at: string
  candidate?: Candidate
  job_role?: JobRole
  last_message?: Message
  unread_count: number
}

type FilterTab = 'ALL' | 'UNREAD' | 'SMS' | 'WHATSAPP'

function getInitials(name?: string): string {
  if (!name) return '??'
  const parts = name.trim().split(' ')
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

function getCandidateName(conv: Conversation): string {
  const c = conv.candidate
  return c?.name || c?.full_name || c?.email || 'Unknown'
}

function relativeTime(iso?: string): string {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function statusIcon(status: string, read_at?: string): string {
  if (read_at || status === 'READ') return '✓✓'
  if (status === 'DELIVERED') return '✓✓'
  return '✓'
}

export const MessagingInbox: React.FC = () => {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [selectedConv, setSelectedConv] = useState<Conversation | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [filter, setFilter] = useState<FilterTab>('ALL')
  const [messageBody, setMessageBody] = useState('')
  const [channel, setChannel] = useState<'SMS' | 'WHATSAPP'>('SMS')
  const [sending, setSending] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const fetchConversations = async () => {
    try {
      const params: Record<string, string> = {}
      if (filter === 'UNREAD') params.status = 'UNREAD'
      const res = await apiClient.get('/engagement/conversations', { params })
      let data: Conversation[] = res.data || []
      if (filter === 'SMS') data = data.filter(c => c.channel === 'SMS')
      if (filter === 'WHATSAPP') data = data.filter(c => c.channel === 'WHATSAPP')
      setConversations(data)
    } catch (e) {
      console.error('Failed to fetch conversations', e)
    }
  }

  useEffect(() => {
    fetchConversations()
    const interval = setInterval(fetchConversations, 30000)
    return () => clearInterval(interval)
  }, [filter])

  const selectConversation = async (conv: Conversation) => {
    setSelectedConv(conv)
    try {
      const res = await apiClient.get(`/engagement/conversations/${conv.id}/messages`)
      setMessages(res.data || [])
      await apiClient.post(`/engagement/conversations/${conv.id}/mark-read`)
      fetchConversations()
    } catch (e) {
      console.error('Failed to load messages', e)
    }
  }

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async () => {
    if (!selectedConv || !messageBody.trim()) return
    setSending(true)
    try {
      const res = await apiClient.post('/engagement/messages/send', {
        candidate_id: selectedConv.candidate_id,
        job_role_id: selectedConv.job_role_id || null,
        body: messageBody.trim(),
        channel,
      })
      setMessages(prev => [...prev, res.data])
      setMessageBody('')
      fetchConversations()
    } catch (e) {
      console.error('Send failed', e)
    } finally {
      setSending(false)
    }
  }

  const filterTabs: FilterTab[] = ['ALL', 'UNREAD', 'SMS', 'WHATSAPP']

  return (
    <div className="flex h-full -m-6 overflow-hidden">
      {/* Left panel */}
      <div className="w-72 flex-shrink-0 border-r border-gray-200 bg-white flex flex-col">
        <div className="px-4 py-4 border-b border-gray-200">
          <h2 className="text-lg font-bold text-gray-900">Messages</h2>
          <div className="flex gap-1 mt-3">
            {filterTabs.map(tab => (
              <button
                key={tab}
                onClick={() => setFilter(tab)}
                className={`px-2 py-1 rounded text-xs font-medium transition ${
                  filter === tab
                    ? 'bg-purple-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {tab === 'WHATSAPP' ? 'WA' : tab}
              </button>
            ))}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          {conversations.length === 0 && (
            <div className="p-6 text-center text-gray-400 text-sm">No conversations</div>
          )}
          {conversations.map(conv => {
            const name = getCandidateName(conv)
            const preview = conv.last_message?.body?.slice(0, 40) || ''
            const isSelected = selectedConv?.id === conv.id
            return (
              <button
                key={conv.id}
                onClick={() => selectConversation(conv)}
                className={`w-full text-left px-4 py-3 flex items-start gap-3 hover:bg-gray-50 transition border-b border-gray-100 ${
                  isSelected ? 'bg-purple-50' : ''
                }`}
              >
                <div className="w-10 h-10 rounded-full bg-purple-600 flex items-center justify-center text-white text-sm font-bold flex-shrink-0">
                  {getInitials(name)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-gray-900 text-sm truncate">{name}</span>
                    <span className="text-xs text-gray-400 flex-shrink-0 ml-1">{relativeTime(conv.last_message_at)}</span>
                  </div>
                  <div className="text-xs text-gray-500 truncate">{conv.job_role?.title || ''}</div>
                  <div className="flex items-center justify-between mt-0.5">
                    <span className="text-xs text-gray-400 truncate">{preview}</span>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      {conv.unread_count > 0 && (
                        <span className="w-2 h-2 rounded-full bg-purple-600"></span>
                      )}
                      <span className={`text-xs px-1 rounded ${conv.channel === 'WHATSAPP' ? 'bg-green-100 text-green-700' : 'bg-blue-100 text-blue-700'}`}>
                        {conv.channel === 'WHATSAPP' ? 'WA' : 'SMS'}
                      </span>
                    </div>
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex flex-col bg-gray-50">
        {!selectedConv ? (
          <div className="flex-1 flex items-center justify-center text-gray-400">
            <div className="text-center">
              <MessageSquare className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="text-lg font-medium">Select a conversation</p>
              <p className="text-sm">Choose a conversation from the left to start messaging</p>
            </div>
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-4">
              <div className="w-10 h-10 rounded-full bg-purple-600 flex items-center justify-center text-white font-bold">
                {getInitials(getCandidateName(selectedConv))}
              </div>
              <div>
                <div className="font-semibold text-gray-900">{getCandidateName(selectedConv)}</div>
                <div className="text-xs text-gray-500 flex items-center gap-2">
                  <span>{selectedConv.job_role?.title || 'No role'}</span>
                  <span className={`px-1.5 py-0.5 rounded text-xs ${selectedConv.channel === 'WHATSAPP' ? 'bg-green-100 text-green-700' : 'bg-blue-100 text-blue-700'}`}>
                    {selectedConv.channel}
                  </span>
                </div>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-3">
              {messages.map(msg => {
                if (msg.sender_type === 'RECRUITER') {
                  return (
                    <div key={msg.id} className="flex justify-end">
                      <div className="max-w-sm">
                        <div className="bg-purple-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm">
                          {msg.body}
                        </div>
                        <div className="flex items-center justify-end gap-1 mt-1">
                          <span className="text-xs text-gray-400">{relativeTime(msg.sent_at)}</span>
                          <span className={`text-xs ${msg.read_at ? 'text-blue-500' : 'text-gray-400'}`}>
                            {statusIcon(msg.status, msg.read_at)}
                          </span>
                        </div>
                      </div>
                    </div>
                  )
                }
                if (msg.sender_type === 'SYSTEM') {
                  return (
                    <div key={msg.id} className="flex justify-center">
                      <span className="text-xs text-gray-400 italic bg-gray-100 px-3 py-1 rounded-full">{msg.body}</span>
                    </div>
                  )
                }
                return (
                  <div key={msg.id} className="flex justify-start">
                    <div className="max-w-sm">
                      <div className="bg-gray-100 text-gray-900 rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm">
                        {msg.body}
                      </div>
                      <div className="flex items-center gap-1 mt-1">
                        <span className="text-xs text-gray-400">{relativeTime(msg.sent_at)}</span>
                      </div>
                    </div>
                  </div>
                )
              })}
              <div ref={messagesEndRef} />
            </div>

            {/* Input bar */}
            <div className="bg-white border-t border-gray-200 px-4 py-3">
              <div className="flex items-end gap-2">
                <button
                  onClick={() => setChannel(c => c === 'SMS' ? 'WHATSAPP' : 'SMS')}
                  className={`flex-shrink-0 px-3 py-2 rounded-lg text-xs font-medium border transition ${
                    channel === 'WHATSAPP'
                      ? 'bg-green-50 border-green-300 text-green-700'
                      : 'bg-blue-50 border-blue-300 text-blue-700'
                  }`}
                >
                  {channel === 'WHATSAPP' ? 'WA' : 'SMS'}
                </button>
                <textarea
                  rows={2}
                  value={messageBody}
                  onChange={e => setMessageBody(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() } }}
                  placeholder="Type a message..."
                  className="flex-1 resize-none border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                />
                <button
                  onClick={sendMessage}
                  disabled={sending || !messageBody.trim()}
                  className="flex-shrink-0 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white p-2.5 rounded-lg transition"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default MessagingInbox
