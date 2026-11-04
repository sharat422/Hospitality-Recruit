"""Property-scoped accommodation and employee transport operations."""
from datetime import date,time
from typing import Annotated,Literal,Optional
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from app.core.dependencies import SupabaseClient
from app.core.security import get_current_user
from app.services.rbac_service import authorize,build_access_context
from app.services.accommodation_transport_service import allocate_bed,assign_transport,checkout,now,rows
router=APIRouter();CurrentUser=Annotated[dict,Depends(get_current_user)]
class BuildingBody(BaseModel):property_id:str;name:str=Field(min_length=2,max_length=160);address:Optional[str]=None;gender_policy:Literal['MALE','FEMALE','MIXED','OTHER']='MIXED';warden_name:Optional[str]=None;warden_phone:Optional[str]=None
class RoomBody(BaseModel):property_id:str;building_id:str;room_number:str;floor_label:Optional[str]=None;room_type:str='SHARED';capacity:int=Field(gt=0,le=100);monthly_charge_inr:float=Field(0,ge=0)
class BedBody(BaseModel):property_id:str;room_id:str;bed_label:str
class AllocationBody(BaseModel):property_id:str;employee_id:str;bed_id:str;expected_check_out:Optional[date]=None;deposit_inr:float=Field(0,ge=0);notes:Optional[str]=None
class MaintenanceBody(BaseModel):property_id:str;building_id:Optional[str]=None;room_id:Optional[str]=None;bed_id:Optional[str]=None;category:str='GENERAL';description:str=Field(min_length=5,max_length=3000);severity:Literal['LOW','MEDIUM','HIGH','CRITICAL']='MEDIUM'
class MaintenanceUpdate(BaseModel):status:Literal['ASSIGNED','IN_PROGRESS','RESOLVED','CANCELLED'];assigned_to:Optional[str]=None;resolution_notes:Optional[str]=None
class RouteBody(BaseModel):property_id:str;name:str=Field(min_length=2);origin:Optional[str]=None;destination:Optional[str]=None;distance_km:Optional[float]=Field(None,ge=0);estimated_minutes:Optional[int]=Field(None,ge=0)
class PointBody(BaseModel):property_id:str;route_id:str;name:str;address:Optional[str]=None;latitude:Optional[float]=None;longitude:Optional[float]=None;stop_order:int=Field(ge=1);default_pickup_time:Optional[time]=None
class VehicleBody(BaseModel):property_id:str;registration_number:str;vehicle_type:Optional[str]=None;capacity:int=Field(gt=0,le=200);provider_name:Optional[str]=None;insurance_expiry:Optional[date]=None;fitness_expiry:Optional[date]=None
class DriverBody(BaseModel):property_id:str;employee_id:Optional[str]=None;name:str;phone:str;licence_number_masked:Optional[str]=None;licence_expiry:Optional[date]=None
class ScheduleBody(BaseModel):property_id:str;route_id:str;vehicle_id:str;driver_id:str;service_date:date;departure_time:time;arrival_time:Optional[time]=None;shift_type:Optional[str]=None
class AssignmentBody(BaseModel):property_id:str;employee_id:str;schedule_id:str;pickup_point_id:str
def scoped(sb,c,table,item_id):
 found=rows(sb.table(table).select('*').eq('id',item_id).eq('org_id',c.org_id).limit(1).execute())
 if not found:raise HTTPException(404,'Record not found')
 return found[0]
def create(sb,c,table,body):
 authorize(c,'employees.manage',property_id=body.property_id);payload={**body.model_dump(mode='json'),'org_id':c.org_id};saved=rows(sb.table(table).insert(payload).execute());return saved[0] if saved else payload

@router.get('/accommodation/inventory')
async def inventory(property_id:str,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);authorize(c,'employees.read',property_id=property_id)
 buildings=rows(supabase.table('accommodation_buildings').select('*').eq('org_id',c.org_id).eq('property_id',property_id).order('name').execute());rooms=rows(supabase.table('accommodation_rooms').select('*').eq('org_id',c.org_id).eq('property_id',property_id).execute());beds=rows(supabase.table('accommodation_beds').select('*').eq('org_id',c.org_id).eq('property_id',property_id).execute());active=rows(supabase.table('accommodation_allocations').select('*').eq('org_id',c.org_id).eq('property_id',property_id).in_('status',['ALLOCATED','CHECKED_IN']).execute())
 maintenance=rows(supabase.table('accommodation_maintenance_requests').select('*').eq('org_id',c.org_id).eq('property_id',property_id).order('created_at',desc=True).limit(100).execute())
 return {'buildings':buildings,'rooms':rooms,'beds':beds,'active_allocations':active,'maintenance':maintenance,'occupancy':{'total_beds':len([x for x in beds if x['status']!='INACTIVE']),'occupied':len(active),'available':len([x for x in beds if x['status']=='AVAILABLE'])}}
@router.post('/accommodation/buildings',status_code=201)
async def building(body:BuildingBody,supabase:SupabaseClient,user:CurrentUser):return create(supabase,build_access_context(supabase,user),'accommodation_buildings',body)
@router.post('/accommodation/rooms',status_code=201)
async def room(body:RoomBody,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);parent=scoped(supabase,c,'accommodation_buildings',body.building_id)
 if parent['property_id']!=body.property_id:raise HTTPException(422,'Building belongs to another property')
 return create(supabase,c,'accommodation_rooms',body)
@router.post('/accommodation/beds',status_code=201)
async def bed(body:BedBody,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);parent=scoped(supabase,c,'accommodation_rooms',body.room_id);authorize(c,'employees.manage',property_id=body.property_id)
 if parent['property_id']!=body.property_id:raise HTTPException(422,'Room belongs to another property')
 count=rows(supabase.table('accommodation_beds').select('id').eq('room_id',body.room_id).execute())
 if len(count)>=int(parent['capacity']):raise HTTPException(409,'Room bed capacity has been reached')
 return create(supabase,c,'accommodation_beds',body)
@router.post('/accommodation/allocations',status_code=201)
async def allocation(body:AllocationBody,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);authorize(c,'employees.manage',property_id=body.property_id);return allocate_bed(supabase,org_id=c.org_id,actor_id=c.user_id,**body.model_dump(mode='json'))
@router.post('/accommodation/allocations/{allocation_id}/check-in')
async def checkin(allocation_id:str,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);item=scoped(supabase,c,'accommodation_allocations',allocation_id);authorize(c,'employees.manage',property_id=item['property_id'])
 if item['status']!='ALLOCATED':raise HTTPException(409,'Only an allocated bed can be checked in')
 values={'status':'CHECKED_IN','check_in_at':now(),'updated_at':now()};saved=rows(supabase.table('accommodation_allocations').update(values).eq('id',allocation_id).eq('status','ALLOCATED').execute());return saved[0] if saved else {**item,**values}
@router.post('/accommodation/allocations/{allocation_id}/check-out')
async def check_out(allocation_id:str,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);item=scoped(supabase,c,'accommodation_allocations',allocation_id);authorize(c,'employees.manage',property_id=item['property_id']);return checkout(supabase,item,c.user_id)
@router.post('/accommodation/maintenance',status_code=201)
async def maintenance(body:MaintenanceBody,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);authorize(c,'employees.read',property_id=body.property_id,owner_user_id=c.user_id);payload={**body.model_dump(),'org_id':c.org_id,'reported_by':c.user_id};saved=rows(supabase.table('accommodation_maintenance_requests').insert(payload).execute());return saved[0] if saved else payload
@router.patch('/accommodation/maintenance/{request_id}')
async def maintenance_update(request_id:str,body:MaintenanceUpdate,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);item=scoped(supabase,c,'accommodation_maintenance_requests',request_id);authorize(c,'employees.manage',property_id=item['property_id']);values={**body.model_dump(),'resolved_at':now() if body.status=='RESOLVED' else None,'updated_at':now()};saved=rows(supabase.table('accommodation_maintenance_requests').update(values).eq('id',request_id).execute());return saved[0] if saved else {**item,**values}

@router.get('/transport/operations')
async def transport_operations(property_id:str,supabase:SupabaseClient,user:CurrentUser,service_date:Optional[date]=None):
 c=build_access_context(supabase,user);authorize(c,'employees.read',property_id=property_id);result={}
 for key,table in [('routes','transport_routes'),('pickup_points','transport_pickup_points'),('vehicles','transport_vehicles'),('drivers','transport_drivers')]:result[key]=rows(supabase.table(table).select('*').eq('org_id',c.org_id).eq('property_id',property_id).execute())
 q=supabase.table('transport_schedules').select('*').eq('org_id',c.org_id).eq('property_id',property_id)
 if service_date:q=q.eq('service_date',service_date.isoformat())
 result['schedules']=rows(q.order('service_date').execute());result['assignments']=rows(supabase.table('employee_transport_assignments').select('*').eq('org_id',c.org_id).eq('property_id',property_id).execute());return result
@router.post('/transport/routes',status_code=201)
async def route(body:RouteBody,supabase:SupabaseClient,user:CurrentUser):return create(supabase,build_access_context(supabase,user),'transport_routes',body)
@router.post('/transport/pickup-points',status_code=201)
async def point(body:PointBody,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);route=scoped(supabase,c,'transport_routes',body.route_id)
 if route['property_id']!=body.property_id:raise HTTPException(422,'Route belongs to another property')
 return create(supabase,c,'transport_pickup_points',body)
@router.post('/transport/vehicles',status_code=201)
async def vehicle(body:VehicleBody,supabase:SupabaseClient,user:CurrentUser):return create(supabase,build_access_context(supabase,user),'transport_vehicles',body)
@router.post('/transport/drivers',status_code=201)
async def driver(body:DriverBody,supabase:SupabaseClient,user:CurrentUser):return create(supabase,build_access_context(supabase,user),'transport_drivers',body)
@router.post('/transport/schedules',status_code=201)
async def schedule(body:ScheduleBody,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);authorize(c,'employees.manage',property_id=body.property_id)
 for table,item_id in [('transport_routes',body.route_id),('transport_vehicles',body.vehicle_id),('transport_drivers',body.driver_id)]:
  if scoped(supabase,c,table,item_id)['property_id']!=body.property_id:raise HTTPException(422,'Route, vehicle and driver must belong to the selected property')
 return create(supabase,c,'transport_schedules',body)
@router.post('/transport/assignments',status_code=201)
async def assignment(body:AssignmentBody,supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);authorize(c,'employees.manage',property_id=body.property_id);schedule=scoped(supabase,c,'transport_schedules',body.schedule_id)
 if schedule['property_id']!=body.property_id:raise HTTPException(422,'Schedule belongs to another property')
 return assign_transport(supabase,org_id=c.org_id,property_id=body.property_id,employee_id=body.employee_id,schedule=schedule,pickup_point_id=body.pickup_point_id,actor_id=c.user_id)
@router.patch('/transport/assignments/{assignment_id}/status')
async def assignment_status(assignment_id:str,status:Literal['BOARDED','NO_SHOW','COMPLETED','CANCELLED'],supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);item=scoped(supabase,c,'employee_transport_assignments',assignment_id);authorize(c,'employees.manage',property_id=item['property_id']);values={'status':status,'boarded_at':now() if status=='BOARDED' else item.get('boarded_at'),'updated_at':now()};saved=rows(supabase.table('employee_transport_assignments').update(values).eq('id',assignment_id).execute());return saved[0] if saved else {**item,**values}
@router.get('/my-services')
async def my_services(supabase:SupabaseClient,user:CurrentUser):
 c=build_access_context(supabase,user);accommodation=rows(supabase.table('accommodation_allocations').select('*,accommodation_beds(*,accommodation_rooms(*,accommodation_buildings(*)))').eq('employee_id',c.user_id).in_('status',['ALLOCATED','CHECKED_IN']).limit(1).execute());transport=rows(supabase.table('employee_transport_assignments').select('*,transport_schedules(*,transport_routes(*)),transport_pickup_points(*)').eq('employee_id',c.user_id).in_('status',['ASSIGNED','BOARDED']).execute());return {'accommodation':accommodation[0] if accommodation else None,'transport':transport}
