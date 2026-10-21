from asset_node import AssetNode

def main():

    asset = AssetNode("truck-01","haul_truck", "localhost", 1883)
    asset.run()

if __name__ == '__main__':  
    main()