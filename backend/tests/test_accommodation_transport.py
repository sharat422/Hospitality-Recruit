from fastapi import HTTPException
import pytest
from tests.conftest import MockSupabase
from app.services.accommodation_transport_service import allocate_bed,assign_transport,checkout,employee_at_property
ORG='11111111-1111-1111-1111-111111111111';PROP='22222222-2222-2222-2222-222222222222';EMP='33333333-3333-3333-3333-333333333333'
def test_employee_must_belong_to_property():
 sb=MockSupabase();sb.configure('users',[{'id':EMP,'org_id':ORG,'active_property_id':'other'}]);sb.configure('property_memberships',[])
 with pytest.raises(HTTPException) as exc:employee_at_property(sb,ORG,EMP,PROP)
 assert exc.value.status_code==422
def test_allocate_bed_and_prevent_second_active_allocation():
 sb=MockSupabase();sb.configure('users',[{'id':EMP,'org_id':ORG,'active_property_id':PROP}]);sb.configure('accommodation_beds',[{'id':'bed','status':'AVAILABLE','room_id':None}]);sb.configure('accommodation_allocations',[],[{'id':'alloc','employee_id':EMP,'bed_id':'bed','status':'ALLOCATED'}]);result=allocate_bed(sb,org_id=ORG,property_id=PROP,employee_id=EMP,bed_id='bed',actor_id='admin');assert result['status']=='ALLOCATED'
 sb=MockSupabase();sb.configure('users',[{'id':EMP,'org_id':ORG,'active_property_id':PROP}]);sb.configure('accommodation_beds',[{'id':'bed2','status':'AVAILABLE'}]);sb.configure('accommodation_allocations',[{'id':'existing'}])
 with pytest.raises(HTTPException):allocate_bed(sb,org_id=ORG,property_id=PROP,employee_id=EMP,bed_id='bed2',actor_id='admin')
def test_checkout_releases_bed():
 sb=MockSupabase();sb.configure('accommodation_allocations',[{'id':'a','status':'CHECKED_OUT'}]);sb.configure('accommodation_beds',[]);result=checkout(sb,{'id':'a','org_id':ORG,'property_id':PROP,'employee_id':EMP,'bed_id':'bed','status':'CHECKED_IN'},'admin');assert result['status']=='CHECKED_OUT'
def test_transport_rejects_wrong_route_pickup():
 sb=MockSupabase();sb.configure('users',[{'id':EMP,'org_id':ORG,'active_property_id':PROP}]);sb.configure('transport_pickup_points',[{'id':'p','route_id':'other'}])
 with pytest.raises(HTTPException) as exc:assign_transport(sb,org_id=ORG,property_id=PROP,employee_id=EMP,schedule={'id':'s','route_id':'r','vehicle_id':'v'},pickup_point_id='p',actor_id='admin')
 assert exc.value.status_code==422
def test_transport_vehicle_capacity_is_enforced():
 sb=MockSupabase();sb.configure('users',[{'id':EMP,'org_id':ORG,'active_property_id':PROP}]);sb.configure('transport_pickup_points',[{'id':'p','route_id':'r'}]);sb.configure('employee_transport_assignments',[{'id':'one'}]);sb.configure('transport_vehicles',[{'capacity':1,'status':'ACTIVE'}])
 with pytest.raises(HTTPException) as exc:assign_transport(sb,org_id=ORG,property_id=PROP,employee_id=EMP,schedule={'id':'s','route_id':'r','vehicle_id':'v'},pickup_point_id='p',actor_id='admin')
 assert exc.value.status_code==409
