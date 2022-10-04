from cmath import inf
import queue
from time import sleep
from dronekit import connect,VehicleMode,mavutil,LocationLocal
from controllers.NED_controllers import PID
import time

class OffboardCommander:
    _controller = None
    _estimateQueue = None
    _connection_address = None
    _drone = None

    def __init__(self, connection_address, inputQueue, controller) -> None:
        self._controller = controller
        self._estimateQueue = inputQueue
        self._connection_address = connection_address
        
       
    
    def check_if_connected(self):
        for state in self._drone.core.connection_state():
            if state.is_connected:
                print(f"-- Connected to drone!")
                break


        
    def arm_drone(self):
        self._drone = connect("udpin:0.0.0.0:14550",wait_ready=True)

        while not self._drone.is_armable:
            print(" Waiting for vehicle to initialise...")
            time.sleep(1)
        
        
        print("-- Arming")
        self._drone.mode = VehicleMode("GUIDED")
        self._drone.armed = True

        while not self._drone.armed:
                print(" Waiting for arming...")
                time.sleep(1)



        print("armed")
        


    def takeoff(self,height):
        self._drone.simple_takeoff(height)
           
    def start_fsm(self):
        self.arm_drone()
        self.takeoff(5)
        time.sleep(8)
        self.precision_landing()
    '''
    async def enable_offboard(self):
        await self._drone.offboard.set_position_ned(PositionNedYaw(0.0, 0.0, 0.0, 0.0))
        print("-- Starting offboard")
        try:
            await self._drone.offboard.start()
        except OffboardError as error:
            print(
                f"Starting offboard mode failed with error code: {error._result.result}"
            )
            print("-- Disarming")
            await self._drone.action.disarm()
            return

        print("Offboard mode activated")

    async def set_stage_xy(self):
        await self._drone.offboard.set_position_ned(PositionNedYaw(0, 0, -2, 1.57))

    async def aruco_stream_active(self):
        initial = self._estimateQueue.qsize()
        await asyncio.sleep(1)
        final = self._estimateQueue.qsize()

        return not final == initial
       '''
    def goto_position_target_local_ned(self,north, east, down):
        """
        Send SET_POSITION_TARGET_LOCAL_NED command to request the vehicle fly to a specified
        location in the North, East, Down frame.
        """
        msg = self._drone.message_factory.set_position_target_local_ned_encode(
            0,       # time_boot_ms (not used)
            0, 0,    # target system, target component
            mavutil.mavlink.MAV_FRAME_BODY_OFFSET_NED, # frame
            0b0000111111111000, # type_mask (only positions enabled)
            north, east, 0,
            0, 0, 0, # x, y, z velocity in m/s  (not used)
            0, 0, 0, # x, y, z acceleration (not supported yet, ignored in GCS_Mavlink)
            0, 0)    # yaw, yaw_rate (not supported yet, ignored in GCS_Mavlink)
        # send command to vehicle
        self._drone.send_mavlink(msg)
    def condition_yaw(self,heading, relative=False):
        """
        Send MAV_CMD_CONDITION_YAW message to point vehicle at a specified heading (in degrees).
        This method sets an absolute heading by default, but you can set the `relative` parameter
        to `True` to set yaw relative to the current yaw heading.
        By default the yaw of the vehicle will follow the direction of travel. After setting 
        the yaw using this function there is no way to return to the default yaw "follow direction 
        of travel" behaviour (https://github.com/diydrones/ardupilot/issues/2427)
        For more information see: 
        http://copter.ardupilot.com/wiki/common-mavlink-mission-command-messages-mav_cmd/#mav_cmd_condition_yaw
        """
        if relative:
            is_relative = 1 #yaw relative to direction of travel
        else:
            is_relative = 0 #yaw is an absolute angle
        # create the CONDITION_YAW command using command_long_encode()
        msg = self._drone.message_factory.command_long_encode(
            0, 0,    # target system, target component
            mavutil.mavlink.MAV_CMD_CONDITION_YAW, #command
            0, #confirmation
            abs(heading),    # param 1, yaw in degrees
            50 ,          # param 2, yaw speed deg/s
            round(abs(heading)/heading),          # param 3, direction -1 ccw, 1 cw
            is_relative, # param 4, relative offset 1, absolute angle 0
            0, 0, 0)    # param 5 ~ 7 not used
        # send command to vehicle
        self._drone.send_mavlink(msg)
    
    def send_ned_velocity(self,velocity_x, velocity_y, velocity_z,yaw_rate):
        """
        Move vehicle in direction based on specified velocity vectors and
        for the specified duration.

        This uses the SET_POSITION_TARGET_LOCAL_NED command with a type mask enabling only 
        velocity components 
        (http://dev.ardupilot.com/wiki/copter-commands-in-guided-mode/#set_position_target_local_ned).
        
        Note that from AC3.3 the message should be re-sent every second (after about 3 seconds
        with no message the velocity will drop back to zero). In AC3.2.1 and earlier the specified
        velocity persists until it is canceled. The code below should work on either version 
        (sending the message multiple times does not cause problems).
        
        See the above link for information on the type_mask (0=enable, 1=ignore). 
        At time of writing, acceleration and yaw bits are ignored.
        """
        msg = self._drone.message_factory.set_position_target_local_ned_encode(
            0,       # time_boot_ms (not used)
            0, 0,    # target system, target component
            mavutil.mavlink.MAV_FRAME_BODY_NED, # frame
            0b111111000111, # type_mask (only speeds enabled)
            0, 0, 0, # x, y, z positions (not used)
            velocity_x, velocity_y, velocity_z, # x, y, z velocity in m/s
            0, 0, 0, # x, y, z acceleration (not supported yet, ignored in GCS_Mavlink)
            0, yaw_rate)    # yaw, yaw_rate (not supported yet, ignored in GCS_Mavlink) 
        self._drone.send_mavlink(msg)
     
       
    def send_land_message(self,x,y,z,yaw):
        msg = self._drone.message_factory.landing_target_encode(
            0,          # time since system boot, not used
            0,          # target num, not used
            mavutil.mavlink.MAV_FRAME_BODY_NED, # frame, not used
            x,
            y,
            z,          # distance, in meters
            0,          # Target x-axis size, in radians
            0           # Target y-axis size, in radians
        )
            
    def precision_landing(self):
        


        # start PID
        controller_x = PID()
        controller_y = PID()
        controller_yaw = PID()

        descent_speed = 0.4
       
        time_when_state_last_steady = 0
        
        OFFSET_X = 0
        OFFSET_Y = 0

        ERROR_MARGIN = 10
        while not self._estimateQueue.empty():
            self._estimateQueue.get()
        
        while True:
            


            estimate = self._estimateQueue.get()    
            
            if(abs(estimate[1][2])<12):
                time.sleep(2)
                self._drone.mode = VehicleMode("LAND")
                break
            
            ERROR_MARGIN = max(10,estimate[1][2]/10)

            if ( abs(estimate[1][0])   <  ERROR_MARGIN and  abs(estimate[1][1]) <  ERROR_MARGIN ):
                time_when_state_last_steady = time.time()
           
            controller_x.update(estimate[1][0]/100  + OFFSET_X)
            controller_y.update(estimate[1][1]/100  + OFFSET_Y ) 
            
            controller_yaw.update(estimate[0][2])
            print("x:",estimate[1][0]," ,y:",estimate[1][1],",z:",estimate[1][2],",Yaw:",estimate[0][2])
            z_val = 0
            if (time.time() - time_when_state_last_steady < 3):
                z_val=descent_speed/5

            if (time.time() - time_when_state_last_steady < 1):
                z_val=descent_speed
            if (estimate[1][2]<100):
                descent_speed = 0.1
            self.send_ned_velocity(controller_y.output,-controller_x.output,z_val,controller_yaw.output)
            #self.condition_yaw(controller_yaw.output,estimate[0][2],False)
            
     
    