import asyncio
import traceback
from typing import Tuple

from geographiclib.geodesic import Geodesic

from commanders.mavsdk_commander import MAVSDKCommander
from commanders.olympe_commander import OlympeCommander
from controller import MyController

DEBUG = True

# Follow-me constants
MIN_DIST_M = 10.0
FOLLOW_DIST_M = 20.0
ALT_OFFSET_M = 2.0


def compute_follow_point(
    leader_lat: float,
    leader_lon: float,
    follower_lat: float,
    follower_lon: float,
    distance: float,
) -> Tuple[float, float]:
    """
    Compute target latitude/longitude at `distance` meters from leader,
    along the line toward the follower.
    """
    # Use the WGS84 ellipsoid parameters
    geod = Geodesic(6378137, 1 / 298.257223563)  # WGS84 parameters (a=semi-major axis, f=flattening)
    inv = geod.Inverse(leader_lat, leader_lon, follower_lat, follower_lon)
    bearing = inv["azi1"]
    dest = geod.Direct(leader_lat, leader_lon, bearing, distance)
    return dest["lat2"], dest["lon2"]


async def follow_loop(leader: MAVSDKCommander, follower: OlympeCommander, interval: float = 1.0) -> None:
    """
    Continuously compute and send follow-me commands
    until drones come closer than MIN_DIST, then land follower.
    """
    # Use the WGS84 ellipsoid parameters
    geod = Geodesic(6378137, 1 / 298.257223563)  # WGS84 parameters (a=semi-major axis, f=flattening)
    try:
        while True:
            # Retrieve positions
            lead_lat, lead_lon, lead_alt = await leader.get_position()
            foll_lat, foll_lon, _ = await follower.get_position()

            # Compute separation
            sep = geod.Inverse(lead_lat, lead_lon, foll_lat, foll_lon)["s12"]
            if sep < MIN_DIST_M:
                print(f"Too close ({sep:.1f}m < {MIN_DIST_M}m) – landing follower.")
                await follower.land()
                break

            # Compute target follow point and desired altitude
            tgt_lat, tgt_lon = compute_follow_point(lead_lat, lead_lon, foll_lat, foll_lon, FOLLOW_DIST_M)
            tgt_alt = lead_alt + ALT_OFFSET_M
            print(f"Moving follower to {tgt_lat:.6f}, {tgt_lon:.6f}, alt {tgt_alt:.1f}m")

            # Send command
            await follower.goto_position(tgt_lat, tgt_lon, tgt_alt)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        print("Follow loop cancelled – stopping both drones by sending pcmds")
        try:
            await follower.set_pcmds(0, 0, 0, 0)
        except Exception as e:
            print(f"Error stopping drones: {e}")
    except KeyboardInterrupt:
        print("Follow loop cancelled – stopping both drones by sending pcmds")
        try:
            await follower.set_pcmds(0, 0, 0, 0)
        except Exception as e:
            print(f"Error stopping drones: {e}")
    except Exception as e:
        print(f"Error in follow loop: {e}")
        traceback.print_exc()
        try:
            await follower.land()
        except Exception as land_error:
            print(f"Error landing follower after exception: {land_error}")


async def manual_control(follower) -> None:
    """Continuously read PS4 controller commands and send them to the drone."""
    try:
        controller = MyController(drone=follower, interface="/dev/input/js1", connecting_using_ds4drv=False)
        controller.listen()
    except asyncio.CancelledError:
        print("Manual control loop cancelled – stopping both drones by sending pcmds")
        try:
            await follower.set_pcmds(0, 0, 0, 0)
        except Exception as e:
            print(f"Error stopping drones: {e}")
    except KeyboardInterrupt:
        print("Follow loop cancelled – stopping both drones by sending pcmds")
        try:
            await follower.set_pcmds(0, 0, 0, 0)
        except Exception as e:
            print(f"Error stopping drones: {e}")
    except Exception as e:
        print(f"Error in follow loop: {e}")
        traceback.print_exc()
        try:
            await follower.land()
        except Exception as land_error:
            print(f"Error landing follower after exception: {land_error}")
    finally:
        print("should destroy controller here")
