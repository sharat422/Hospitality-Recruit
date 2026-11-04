"""Shared property/employee validation and occupancy rules."""
from datetime import datetime,timezone
from fastapi import HTTPException
def rows(r):
 d=getattr(r,"data",None);return d if isinstance(d,list) else ([d] if isinstance(d,dict) else [])
def now():return datetime.now(timezone.utc).isoformat()
def employee_at_property(sb,org_id,employee_id,property_id):
 found=rows(sb.table("users").select("id,org_id,active_property_id,full_name,phone").eq("id",employee_id).eq("org_id",org_id).limit(1).execute())
 if not found:raise HTTPException(404,"Employee not found")
 if found[0].get("active_property_id")!=property_id:
  member=rows(sb.table("property_memberships").select("id").eq("user_id",employee_id).eq("property_id",property_id).eq("is_active",True).limit(1).execute())
  if not member:raise HTTPException(422,"Employee is not assigned to this property")
 return found[0]
def allocate_bed(sb,*,org_id,property_id,employee_id,bed_id,actor_id,expected_check_out=None,deposit_inr=0,notes=None):
 employee_at_property(sb,org_id,employee_id,property_id)
 bed=rows(sb.table("accommodation_beds").select("*").eq("id",bed_id).eq("org_id",org_id).eq("property_id",property_id).limit(1).execute())
 if not bed or bed[0].get("status")!="AVAILABLE":raise HTTPException(409,"Bed is unavailable")
 active=rows(sb.table("accommodation_allocations").select("id").eq("employee_id",employee_id).in_("status",["ALLOCATED","CHECKED_IN"]).limit(1).execute())
 if active:raise HTTPException(409,"Employee already has active accommodation")
 payload={"org_id":org_id,"property_id":property_id,"employee_id":employee_id,"bed_id":bed_id,"allocated_by":actor_id,"expected_check_out":expected_check_out,"deposit_inr":deposit_inr,"notes":notes}
 saved=rows(sb.table("accommodation_allocations").insert(payload).execute());sb.table("accommodation_beds").update({"status":"OCCUPIED","updated_at":now()}).eq("id",bed_id).execute()
 room_id=bed[0].get("room_id")
 if room_id:
  room=rows(sb.table("accommodation_rooms").select("capacity").eq("id",room_id).limit(1).execute());occupied=rows(sb.table("accommodation_beds").select("id").eq("room_id",room_id).eq("status","OCCUPIED").execute())
  if room and len(occupied)>=int(room[0]["capacity"]):sb.table("accommodation_rooms").update({"status":"FULL","updated_at":now()}).eq("id",room_id).execute()
 return saved[0] if saved else payload
def checkout(sb,allocation,actor_id):
 if allocation["status"] not in {"ALLOCATED","CHECKED_IN"}:raise HTTPException(409,"Allocation is not active")
 values={"status":"CHECKED_OUT","check_out_at":now(),"checked_out_by":actor_id,"updated_at":now()};saved=rows(sb.table("accommodation_allocations").update(values).eq("id",allocation["id"]).in_("status",["ALLOCATED","CHECKED_IN"]).execute());bed=rows(sb.table("accommodation_beds").select("room_id").eq("id",allocation["bed_id"]).limit(1).execute());sb.table("accommodation_beds").update({"status":"AVAILABLE","updated_at":now()}).eq("id",allocation["bed_id"]).execute()
 if bed and bed[0].get("room_id"):sb.table("accommodation_rooms").update({"status":"AVAILABLE","updated_at":now()}).eq("id",bed[0]["room_id"]).neq("status","MAINTENANCE").execute()
 return saved[0] if saved else {**allocation,**values}
def assign_transport(sb,*,org_id,property_id,employee_id,schedule,pickup_point_id,actor_id):
 employee_at_property(sb,org_id,employee_id,property_id)
 point=rows(sb.table("transport_pickup_points").select("id,route_id").eq("id",pickup_point_id).eq("property_id",property_id).limit(1).execute())
 if not point or point[0]["route_id"]!=schedule["route_id"]:raise HTTPException(422,"Pickup point does not belong to the scheduled route")
 assigned=rows(sb.table("employee_transport_assignments").select("id").eq("schedule_id",schedule["id"]).in_("status",["ASSIGNED","BOARDED"]).execute())
 vehicle=rows(sb.table("transport_vehicles").select("capacity,status").eq("id",schedule["vehicle_id"]).limit(1).execute())
 if not vehicle or vehicle[0]["status"]!="ACTIVE" or len(assigned)>=int(vehicle[0]["capacity"]):raise HTTPException(409,"Vehicle is unavailable or full")
 payload={"org_id":org_id,"property_id":property_id,"employee_id":employee_id,"schedule_id":schedule["id"],"pickup_point_id":pickup_point_id,"assigned_by":actor_id};saved=rows(sb.table("employee_transport_assignments").insert(payload).execute());return saved[0] if saved else payload
