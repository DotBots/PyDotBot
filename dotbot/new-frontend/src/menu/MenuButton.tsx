import {
  Popover,
  PopoverTrigger,
  PopoverContent,
  PopoverArrow,
  PopoverHeader,
  PopoverBody,
  IconButton,
  Tooltip,
  PlacementWithLogical,
  Box,
} from "@chakra-ui/react";

interface MenuButtonProps {
  label: string;
  tooltipPlacement: PlacementWithLogical;
  icon: JSX.Element;
  popoverPlacement: PlacementWithLogical;
  popoverContent: JSX.Element;
}

/**
 * Component for a button with icon, tooltip and popover.
 * It's necessary to forward the ref to the Button component,
 * as it's used in the PopoverTrigger.
 */
export const MenuButton = ({
  label,
  tooltipPlacement,
  icon,
  popoverPlacement,
  popoverContent,
}: MenuButtonProps) => {
  return (
    <Popover placement={popoverPlacement}>
      <Tooltip hasArrow label={label} placement={tooltipPlacement}>
        <Box display="inline-block">
          <PopoverTrigger>
            <IconButton
              fontSize="25px"
              aria-label={label}
              icon={icon}
            ></IconButton>
          </PopoverTrigger>
        </Box>
      </Tooltip>
      <PopoverContent>
        <PopoverArrow />
        <PopoverHeader>{label}</PopoverHeader>
        <PopoverBody>{popoverContent}</PopoverBody>
      </PopoverContent>
    </Popover>
  );
};
